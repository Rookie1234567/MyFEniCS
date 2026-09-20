"""The previously qualified small PORD64 p4/MPC fixture, with ICNTL(23)."""

import os
from pathlib import Path

import numpy as np
import pytest
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI
from petsc4py import PETSc
import dolfinx_mpc

from src.solvers.fullspace_v17_p3_oracle import _MumpsFactor

pytestmark = pytest.mark.skipif(
    os.environ.get("TASK39EXTRA_PORD64_ACTIVATION") != "1",
    reason="PORD64 fixture requires scripts/activate_task39extra_pord64.sh",
)


def test_pord64_small_p4_mpc_mumps_roundtrip():
    domain = mesh.create_unit_cube(
        MPI.COMM_SELF, 2, 2, 2, cell_type=mesh.CellType.hexahedron
    )
    space = fem.functionspace(
        domain,
        element("N1curl", domain.basix_cell(), 4, dtype=default_real_type),
    )
    u, v = ufl.TrialFunction(space), ufl.TestFunction(space)
    form = fem.form(
        (ufl.inner(ufl.curl(u), ufl.curl(v)) + ufl.inner(u, v)) *
        ufl.dx(domain=domain)
    )
    owned_rows = int(space.dofmap.index_map.size_local)
    mpc = dolfinx_mpc.MultiPointConstraint(space)
    mpc.add_constraint(
        space,
        np.asarray([owned_rows - 1], dtype=np.int32),
        np.asarray([0], dtype=np.int64),
        np.asarray([0.5 + 0.25j], dtype=PETSc.ScalarType),
        np.asarray([0], dtype=np.int32),
        np.asarray([0, 1], dtype=np.int32),
    )
    mpc.finalize()
    matrix = dolfinx_mpc.assemble_matrix(form, mpc, bcs=[])
    matrix.assemble()
    b = matrix.createVecRight()
    x = b.duplicate()
    residual = b.duplicate()
    factor = None
    try:
        PETSc.Options()["mat_mumps_icntl_7"] = 4
        b.set(PETSc.ScalarType(1.0 + 0.125j))
        b.assemble()
        factor = _MumpsFactor(matrix)
        factor.set_icntl(23, 0)
        factor.symbolic(matrix)
        info = factor.info((1, 7, 16))
        assert factor.get_icntl(23) == 0
        factor.numeric(matrix)
        factor.solve(b, x)
        matrix.mult(x, residual)
        residual.aypx(-1, b)
        relative = float(residual.norm() / max(b.norm(), np.finfo(float).tiny))
        assert int(domain.topology.index_map(domain.topology.dim).size_local) == 8
        assert int(matrix.getInfo()["nz_used"]) == 701496
        assert np.dtype(PETSc.IntType) == np.dtype(np.int64)
        assert np.dtype(PETSc.ScalarType) == np.dtype(np.complex128)
        assert int(info["infog"]["1"]) == 0
        assert int(info["infog"]["7"]) == 4
        assert factor.symbolic_calls == factor.numeric_calls == factor.solve_calls == 1
        assert relative < 1e-10
        maps = {
            Path(fields[-1]).resolve()
            for line in Path("/proc/self/maps").read_text().splitlines()
            if (fields := line.split()) and fields[-1].startswith("/")
        }
        petsc_maps = {path for path in maps if path.name.startswith("libpetsc")}
        assert petsc_maps == {Path(
            "/tmp/task39extra-pord64/petsc/lib/libpetsc.so.3.19.6"
        )}
    finally:
        try:
            del PETSc.Options()["mat_mumps_icntl_7"]
        except KeyError:
            pass
        if factor is not None:
            factor.destroy()
        for value in (residual, x, b, matrix):
            value.destroy()
