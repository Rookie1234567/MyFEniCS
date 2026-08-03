from types import SimpleNamespace

import dolfinx_mpc
import numpy as np
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers import physical_slab_two_level as slab_module


def test_active_trace_floquet_basis_uses_real_hcurl_and_mapped_rows():
    comm = MPI.COMM_WORLD
    msh = mesh.create_unit_cube(comm, 1, 1, 24, cell_type=mesh.CellType.hexahedron)
    V = fem.functionspace(
        msh,
        element("N1curl", msh.basix_cell(), 3, dtype=default_real_type),
    )
    template = fem.Function(V)
    full_vector = template.x.petsc_vec
    full_rows = int(full_vector.getSize())
    start, end = full_vector.getOwnershipRange()
    global_local = V.dofmap.index_map.local_to_global(
        np.asarray([0, 1], dtype=np.int32)
    )
    master, slave_global = map(int, global_local)
    mpc = dolfinx_mpc.MultiPointConstraint(V)
    mpc.add_constraint(
        V,
        np.asarray([1], dtype=np.int32),
        np.asarray([master], dtype=np.int64),
        np.asarray([0.5 + 0.25j], dtype=PETSc.ScalarType),
        np.asarray([comm.rank], dtype=np.int32),
        np.asarray([0, 1], dtype=np.int32),
    )
    mpc.finalize()
    first_values = None
    calls = 0
    slave_zero = True

    def homogenize(field):
        nonlocal calls, first_values, slave_zero
        mpc.homogenize(field)
        values = field.x.petsc_vec.getValues(owned_active)
        if calls == 0:
            first_values = values.copy()
        calls += 1
        slave_zero = slave_zero and field.x.petsc_vec.getValue(slave_global) == 0.0

    excluded = set(range(4, full_rows, 4))
    excluded.difference_update(comm.allgather(master))
    excluded.update(comm.allgather(slave_global))
    active_originals = np.array(
        sorted(set(range(full_rows)) - excluded), dtype=PETSc.IntType
    )
    active_rows = len(active_originals)
    original_to_active = dict(
        zip(active_originals.tolist(), range(active_rows - 1, -1, -1))
    )
    owned_active = active_originals[
        (active_originals >= start) & (active_originals < end)
    ]
    condensed = SimpleNamespace(
        trace_constraints=SimpleNamespace(
            owned_active_original_dofs=owned_active,
            original_to_active=original_to_active,
        )
    )
    fine = PETSc.Mat().createAIJ(size=(active_rows, active_rows), nnz=1, comm=comm)
    fine.setUp()
    fine.assemble()
    config = SimpleNamespace(domain_z_min=0.0, domain_z_max=1.0, kx=0.2, ky=0.3)
    floquet_data = SimpleNamespace(mpc=SimpleNamespace(homogenize=homogenize))
    try:
        basis = slab_module.build_active_trace_floquet_basis(
            condensed, V, config, floquet_data, fine
        )
        assert len(basis) == 75
        assert not np.array_equal(
            active_originals[:active_rows],
            np.arange(active_rows, dtype=PETSc.IntType),
        )
        assert all(
            np.all((vector.indices >= 0) & (vector.indices < active_rows))
            for vector in basis
        )
        assert calls == 75
        assert slave_zero

        active_ids = np.fromiter(
            (original_to_active[int(value)] for value in owned_active),
            dtype=PETSc.IntType,
        )
        expected = fine.createVecRight()
        expected.setValues(active_ids, first_values)
        expected.assemble()
        expected.scale(1.0 / expected.norm())
        actual = fine.createVecRight()
        actual.setValues(basis[0].indices, basis[0].values)
        actual.assemble()
        actual_array = actual.getArray(readonly=True)
        expected_array = expected.getArray(readonly=True)
        np.testing.assert_allclose(
            actual_array, expected_array, rtol=2.0e-12, atol=2.0e-12
        )

        vectors = []
        for sparse_vector in basis:
            vector = fine.createVecRight()
            vector.setValues(sparse_vector.indices, sparse_vector.values)
            vector.assemble()
            vectors.append(vector)
        local_basis = np.array([vector.getArray(readonly=True) for vector in vectors]).T
        gram = comm.allreduce(local_basis.conj().T @ local_basis, op=MPI.SUM)
        np.testing.assert_allclose(gram, np.eye(75), rtol=3.0e-11, atol=3.0e-11)
        for vector in (*vectors, actual, expected):
            vector.destroy()
    finally:
        fine.destroy()
