import numpy as np
from petsc4py import PETSc

from src.runners.task40_v10_worker import _assign_vector_storage


def test_assign_vector_storage_uses_public_writable_petsc_array_api():
    vector = PETSc.Vec().createSeq(3, comm=PETSc.COMM_SELF)
    try:
        _assign_vector_storage(vector, np.array([1 + 2j, 3 + 4j, 5 + 6j]))
        _assign_vector_storage(
            vector, np.array([9 + 1j, 8 + 2j]), rows=np.array([0, 2], dtype=np.int64)
        )
        np.testing.assert_array_equal(
            np.asarray(vector.array_r),
            np.array([9 + 1j, 3 + 4j, 8 + 2j], dtype=np.complex128),
        )
    finally:
        vector.destroy()
