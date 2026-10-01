"""Separate-stack qualification of real MPC/port/interior recovery.

The historical V18 test's mathematical assertions are reused with a real
public PETSc KSP factor. Its old private ctypes MUMPS factor is never called:
that ABI helper has an undersized MatFactorInfo on PETSc 3.25. This is not an
identical rerun or a qualification of that historical helper.
"""

import importlib

from petsc4py import PETSc


class PublicPetscFixtureFactor:
    """Actual tiny sparse LU, through version-matched petsc4py APIs only."""

    backend_name = "mumps" if PETSc.Sys.hasExternalPackage("mumps") else "petsc"

    def __init__(self, matrix):
        self.ksp = PETSc.KSP().create(matrix.getComm())
        self.calls = 0
        self.destroyed = False
        try:
            self.ksp.setOperators(matrix)
            self.ksp.setType("preonly")
            pc = self.ksp.getPC()
            pc.setType("lu")
            pc.setFactorSolverType(self.backend_name)
            self.ksp.setUp()
        except BaseException:
            self.ksp.destroy()
            self.destroyed = True
            raise

    def solve_repeated(self, rhs, output):
        self.ksp.solve(rhs, output)
        if self.ksp.getConvergedReason() <= 0:
            raise RuntimeError("public PETSc tiny fixture solve did not converge")
        self.calls += 1

    def destroy(self):
        if not self.destroyed:
            self.ksp.destroy()
            self.destroyed = True


def test_cloud_public_petsc_mpc_nonzero_ports_and_recovery(monkeypatch):
    historical = importlib.import_module("src.test.test_task39extra_v18_cell_condensed_ports")

    def prohibited_old_ffi(*args, **kwargs):
        raise AssertionError("historical private ctypes MUMPS ABI must not execute on this stack")

    monkeypatch.setattr(historical, "_MumpsFactor", prohibited_old_ffi)
    # Replace only the factor factory with another actual sparse LU. The
    # original real-cell assembly, complex MPC, nonzero local Bi/Di/RHS,
    # independent dense oracle, repeated solves and cleanup checks remain.
    monkeypatch.setattr(historical, "Factor", PublicPetscFixtureFactor)
    historical.test_actual_adapter_complex_mpc_nonzero_interior_ports_and_new_rhs()
