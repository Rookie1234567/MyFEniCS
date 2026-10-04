"""Small native CSR oracle from original kernels and literal finalized MPC.

Finite witnesses only. This preserves every cell contribution, including
shared entities and complex multipoint constraints. No factorization occurs.
"""

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix


def assemble_witness_csr(cell_matrices, cell_dofs, expansion, full_rows):
    """Sum E_c^H V_c E_c without recomputing expensive native integrals."""
    expansion = csr_matrix(expansion, dtype=np.complex128)
    if expansion.shape != (full_rows, full_rows) or full_rows > 50000:
        raise ValueError("bounded finite native oracle shape")
    rows, columns, values = [], [], []
    for matrix, dofs in zip(cell_matrices, cell_dofs, strict=True):
        if matrix.shape != (len(dofs), len(dofs)):
            raise ValueError("native original cell matrix shape")
        e = expansion[np.asarray(dofs)]
        a = (e.conjugate().T @ csr_matrix(matrix) @ e).tocoo()
        rows.append(a.row.astype(np.int32, copy=False))
        columns.append(a.col.astype(np.int32, copy=False))
        values.append(a.data)
    r, c, v = np.concatenate(rows), np.concatenate(columns), np.concatenate(values)
    del rows, columns, values
    result = coo_matrix((v, (r, c)), shape=(full_rows, full_rows)).tocsr()
    result.sum_duplicates()
    result.sort_indices()
    return result
