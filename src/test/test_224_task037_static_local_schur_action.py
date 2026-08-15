import unittest

import dolfinx_mpc
import numpy as np
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.static_local_schur_action import (
    create_static_local_schur_action,
    materialize_research_explicit_fine_matrix,
)
from src.solvers.hcurl_cell_static_condensation import (
    owned_hcurl_cell_interior_dofs,
)
from src.solvers.condensed_dtn import (
    PetscCondensedBlocks,
    create_matrix_free_condensed_operator,
    relative_action_error,
)


def _build_fixture(comm):
    mesh_3d = mesh.create_unit_cube(
        comm,
        3,
        3,
        1,
        cell_type=mesh.CellType.hexahedron,
    )
    tdim = mesh_3d.topology.dim
    owned_cells = int(mesh_3d.topology.index_map(tdim).size_local)
    cell_tags = mesh.meshtags(
        mesh_3d,
        tdim,
        np.arange(owned_cells, dtype=np.int32),
        np.ones(owned_cells, dtype=np.int32),
    )
    V = fem.functionspace(
        mesh_3d,
        element(
            "N1curl",
            mesh_3d.basix_cell(),
            2,
            dtype=default_real_type,
        ),
    )
    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    dx = ufl.Measure("dx", domain=mesh_3d, subdomain_data=cell_tags)
    compiled = fem.form(
        (
            ufl.inner(ufl.curl(u), ufl.curl(v))
            + PETSc.ScalarType(2.5 - 0.2j) * ufl.inner(u, v)
        )
        * dx(1)
    )
    return mesh_3d, cell_tags, V, compiled


def _serial_aij(values):
    values = np.asarray(values, dtype=PETSc.ScalarType)
    matrix = PETSc.Mat().createAIJ(
        size=values.shape, nnz=values.shape[1], comm=PETSc.COMM_SELF
    )
    matrix.setValues(
        np.arange(values.shape[0], dtype=PETSc.IntType),
        np.arange(values.shape[1], dtype=PETSc.IntType),
        values,
    )
    matrix.assemble()
    return matrix


def _assert_materialized_matches_assembled(testcase, condensed) -> None:
    materialized = materialize_research_explicit_fine_matrix(condensed)
    source = condensed.matrix.createVecRight()
    expected = condensed.matrix.createVecLeft()
    observed = condensed.matrix.createVecLeft()
    start, end = source.getOwnershipRange()
    values = np.arange(start, end, dtype=np.float64)
    source.getArray()[:] = values + 1j * (values + 1.0)
    source.assemble()
    condensed.matrix.mult(source, expected)
    materialized.mult(source, observed)
    difference = observed.copy()
    difference.axpy(PETSc.ScalarType(-1.0), expected)
    relative = difference.norm() / max(expected.norm(), 1.0e-30)
    testcase.assertLess(relative, 1.0e-11)
    difference.destroy()
    observed.destroy()
    expected.destroy()
    source.destroy()
    materialized.destroy()


class TestTask037StaticLocalSchurAction(unittest.TestCase):
    def test_retained_action_matches_assembled_mpc_schur(self) -> None:
        _mesh, cell_tags, V, compiled = _build_fixture(MPI.COMM_SELF)
        cell_interiors = owned_hcurl_cell_interior_dofs(V)
        interior_set = {int(value) for interior in cell_interiors for value in interior}
        trace_original = [
            value
            for value in range(V.dofmap.index_map.size_global)
            if value not in interior_set
        ]
        master = int(trace_original[0])
        slave = int(trace_original[-1])
        mpc = dolfinx_mpc.MultiPointConstraint(V)
        mpc.add_constraint(
            V,
            np.asarray([slave], dtype=np.int32),
            np.asarray([master], dtype=np.int64),
            np.asarray([0.5 + 0.25j], dtype=PETSc.ScalarType),
            np.asarray([0], dtype=np.int32),
            np.asarray([0, 1], dtype=np.int32),
        )
        mpc.finalize()

        default_system = build_unconstrained_assembly_time_condensation(
            compiled,
            V,
            cell_tags,
            mpc=mpc,
        )
        self.assertIsNone(default_system.retained_local_schur_by_class)
        default_system.destroy()

        condensed = build_unconstrained_assembly_time_condensation(
            compiled,
            V,
            cell_tags,
            mpc=mpc,
            retain_local_schur_for_matrix_free=True,
        )
        retained = condensed.retained_local_schur_by_class
        self.assertIsNotNone(retained)
        assert retained is not None
        cell_maps = condensed.cell_recovery_maps
        unique_keys = {cell.class_key for cell in cell_maps}
        self.assertLess(len(unique_keys), len(cell_maps))
        self.assertEqual(set(retained), unique_keys)
        self.assertTrue(all(not schur.flags.writeable for schur in retained.values()))
        self.assertGreater(
            max(np.linalg.norm(schur - schur.conj().T) for schur in retained.values()),
            1.0e-10,
        )
        self.assertEqual(
            condensed.build_audit["oriented_schur_class_count_sum"],
            len(unique_keys),
        )
        _assert_materialized_matches_assembled(self, condensed)

        action, context = create_static_local_schur_action(
            condensed,
            condensed.matrix,
        )
        self.assertEqual(len(context._cells), len(cell_maps))
        self.assertEqual(len(context._union_indices), condensed.active_rows)

        source = condensed.matrix.createVecRight()
        expected = condensed.matrix.createVecLeft()
        observed = condensed.matrix.createVecLeft()
        values = np.arange(condensed.active_rows, dtype=np.float64)
        source.getArray()[:] = values + 1j * (values + 1.0)
        source.assemble()
        condensed.matrix.mult(source, expected)
        action.mult(source, observed)
        difference = observed.copy()
        difference.axpy(
            PETSc.ScalarType(-1.0),
            expected,
        )
        relative = difference.norm() / max(expected.norm(), 1.0e-30)
        self.assertLess(relative, 1.0e-11)

        difference.destroy()
        observed.destroy()
        expected.destroy()
        source.destroy()
        action.destroy()
        condensed.destroy()

    def test_dtn_shell_uses_retained_local_schur_forward_action(self) -> None:
        _mesh, cell_tags, V, compiled = _build_fixture(MPI.COMM_SELF)
        condensed = build_unconstrained_assembly_time_condensation(
            compiled,
            V,
            cell_tags,
            retain_local_schur_for_matrix_free=True,
        )
        n_fe = condensed.active_rows
        n_aux = 2
        coupling = np.zeros((n_fe, n_aux), dtype=np.complex128)
        coupling[[0, 1, n_fe // 2], [0, 1, 0]] = (
            0.3 - 0.1j,
            -0.2 + 0.05j,
            0.07 + 0.02j,
        )
        fine = condensed.matrix.copy()
        C = _serial_aij(coupling)
        D = _serial_aij(coupling.T * (-1.2 + 0.1j))
        H = _serial_aij([[1.2 + 0.1j, 0.1 - 0.05j], [0.02j, 0.9 - 0.1j]])
        blocks = PetscCondensedBlocks(
            fine, C, D, H, fine.createVecLeft(), H.createVecLeft(), n_fe, n_aux
        )
        action, _ = create_static_local_schur_action(condensed, condensed.matrix)
        assembled_shell, _ = create_matrix_free_condensed_operator(blocks)
        local_shell, _ = create_matrix_free_condensed_operator(
            blocks, fine_operator=action
        )
        source = fine.createVecRight()
        values = np.arange(n_fe, dtype=np.float64)
        source.getArray()[:] = values + 1j * (values + 1.0)
        source.assemble()
        error = relative_action_error(assembled_shell, local_shell, source)
        self.assertLess(error, 1.0e-11)

        for obj in (source, local_shell, assembled_shell, action, blocks, condensed):
            obj.destroy()

    @unittest.skipUnless(
        MPI.COMM_WORLD.size in (2, 4),
        "MPI2/MPI4 owner-scatter qualification",
    )
    def test_mpi_owner_scatter_add_matches_assembled(self) -> None:
        _mesh, cell_tags, V, compiled = _build_fixture(MPI.COMM_WORLD)
        condensed = build_unconstrained_assembly_time_condensation(
            compiled,
            V,
            cell_tags,
            retain_local_schur_for_matrix_free=True,
        )
        _assert_materialized_matches_assembled(self, condensed)
        action, _context = create_static_local_schur_action(
            condensed,
            condensed.matrix,
        )
        source = condensed.matrix.createVecRight()
        expected = condensed.matrix.createVecLeft()
        observed = condensed.matrix.createVecLeft()
        start, end = source.getOwnershipRange()
        values = np.arange(start, end, dtype=np.float64)
        source.getArray()[:] = values + 1j * (values + 1.0)
        source.assemble()
        condensed.matrix.mult(source, expected)
        action.mult(source, observed)
        difference = observed.copy()
        difference.axpy(PETSc.ScalarType(-1.0), expected)
        relative = difference.norm() / max(expected.norm(), 1.0e-30)
        self.assertLess(relative, 1.0e-11)

        difference.destroy()
        observed.destroy()
        expected.destroy()
        source.destroy()
        action.destroy()
        condensed.destroy()


if __name__ == "__main__":
    unittest.main()
