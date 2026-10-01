"""Opt-in fixed p3 ILU(0), exact packet assembly and forty-port correction.

K is an additional global sparse PC matrix, not the outer operator. All
expansion coefficients and local Schur tensors come from the original packet.
No Torch, global exact LU, drop rule, shift, or inner Krylov solve is used.
"""
import ctypes
import os
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy.linalg import lu_factor, lu_solve
from scipy.sparse import coo_matrix, csr_matrix, eye

from src.solvers.neural_fe_action_packet import array_hash


SPEC = dict(type='ilu', levels=0, ordering='natural', shift='NONE',
            communicator='COMM_SELF', matrix='seqaij', out_of_place=True,
            drop=None, diagonal_rescue=False)


def expansions(packet):
    """Small local E, including duplicate constraints, in canonical master order."""
    a = packet.a
    order = np.argsort(a['erows'], kind='stable')
    rows, ids, vals = a['erows'][order], a['eids'][order], a['evals'][order]
    for cell in range(packet.nc):
        lo, hi = np.searchsorted(rows, [cell*packet.lt, (cell+1)*packet.lt])
        local = rows[lo:hi] - cell*packet.lt
        columns, inverse = np.unique(ids[lo:hi], return_inverse=True)
        E = np.zeros((packet.lt, len(columns)), np.complex128)
        np.add.at(E, (local, inverse), vals[lo:hi])
        yield cell, columns, E


def capacity(packet, index_dtype=np.int64):
    """Conservative contribution bound before any global sparse allocation."""
    widths = [len(ids) for _, ids, _ in expansions(packet)]
    contributions = sum(w*w for w in widths) + packet.nt
    item = np.dtype(index_dtype).itemsize
    csr_bound = contributions*(16+item) + (packet.nt+1)*item
    factor_bound = 2*csr_bound + packet.nt*(16+4*item)
    # Packet/Python/FE stack and audits: 2 GiB allowance; each CSR is separately
    # owned; backend symbolic/numeric allowance 4x explicit factor bound. The
    # 256-vector Krylov and forty-column port arrays have independent terms.
    planned = 2*2**30 + 3*csr_bound + 5*factor_bound + packet.nt*(258+120)*16
    row = dict(contribution_nnz_upper=contributions, csr_bytes_upper=csr_bound,
               factor_explicit_payload_upper_bytes=factor_bound,
               simultaneous_planning_upper_bytes=planned, index_dtype=np.dtype(index_dtype).name,
               max_cell_master_width=max(widths), local_tensors_from_original_packet=True,
               backend_workspace_allowance_bytes=4*factor_bound,
               factor_RSS_separately='unknown; measure whole process tree')
    row['qualified'] = (contributions <= 20_000_000 and csr_bound <= 512*2**20
                        and factor_bound <= 2**30 and planned <= 8*2**30)
    return row


def assemble_K(packet, *, index_dtype=np.int64, guard=lambda: None, event=lambda **kw: None):
    plan = capacity(packet, index_dtype)
    if not plan['qualified']:
        raise MemoryError('fixed K/factor conservative capacity failed')
    began = perf_counter()
    pattern = eye(packet.nt, format='csr', dtype=bool)
    chunk_r, chunk_c = [], []
    for cell, ids, _ in expansions(packet):
        guard()
        chunk_r.append(np.repeat(ids, len(ids)))
        chunk_c.append(np.tile(ids, len(ids)))
        if len(chunk_r) == 16 or cell == packet.nc-1:
            r, c = np.concatenate(chunk_r), np.concatenate(chunk_c)
            block = coo_matrix((np.ones(len(r), bool), (r, c)), shape=pattern.shape).tocsr()
            pattern = pattern + block  # Boolean union; no value-based deletion.
            chunk_r.clear(); chunk_c.clear()
    pattern.sum_duplicates(); pattern.sort_indices()
    K = csr_matrix((np.zeros(pattern.nnz, np.complex128),
                    pattern.indices.astype(index_dtype), pattern.indptr.astype(index_dtype)),
                   shape=pattern.shape)
    del pattern
    pattern_seconds = perf_counter()-began
    numeric = perf_counter()
    for cell, ids, E in expansions(packet):
        guard()
        local = E.conj().T @ packet.a['S'][packet.a['classes'][cell]] @ E
        for j, row in enumerate(ids):
            lo, hi = K.indptr[row:row+2]
            positions = lo + np.searchsorted(K.indices[lo:hi], ids)
            if np.any(positions >= hi) or not np.array_equal(K.indices[positions], ids):
                raise ValueError('canonical K structural pattern missing local contribution')
            K.data[positions] += local[j]
        if cell % 64 == 0:
            event(event='K_numeric_chunk', cell=cell)
    if not np.isfinite(K.data).all():
        raise ValueError('nonfinite original K assembly')
    row = dict(plan, nnz=K.nnz, csr_payload_bytes=K.data.nbytes+K.indices.nbytes+K.indptr.nbytes,
               data_sha256=array_hash(K.data), indices_sha256=array_hash(K.indices),
               indptr_sha256=array_hash(K.indptr), pattern_seconds=pattern_seconds,
               numeric_seconds=perf_counter()-numeric, assembly_seconds=perf_counter()-began,
               retained_structural_zeros=True, duplicate_contributions_merged=True,
               outer_action_replaced=False)
    return K, row


def direct_F(packet, trace):
    """Original negative Dhat and direct D, not a full volume action."""
    local = packet._expand(trace)
    return -np.einsum('cpi,ci->p', packet.a['Dhat'], local, optimize=False)-packet._direct_D(trace)


def direct_C(packet, alpha):
    local = np.einsum('ctp,p->ct', packet.a['Bhat'], alpha, optimize=False)
    return packet._pullback(local)+packet._direct_B(alpha)


def no_fill_reference(matrix):
    """Independent bounded fixture only: natural no-fill Doolittle elimination."""
    matrix = np.asarray(matrix)
    if len(matrix) > 128:
        raise ValueError('no-fill reference is small-test-only')
    pattern = matrix != 0
    factors = matrix.copy()
    for i in range(len(matrix)):
        for j in range(i):
            if pattern[i, j]:
                factors[i, j] /= factors[j, j]
                for k in range(j+1, len(matrix)):
                    if pattern[i, k]:
                        factors[i, k] -= factors[i, j]*factors[j, k]
    from scipy.linalg import solve_triangular
    def apply(rhs):
        y = solve_triangular(np.tril(factors, -1)+np.eye(len(matrix)), rhs, lower=True)
        return solve_triangular(np.triu(factors), y)
    return apply


class NativeILU0:
    """Only the existing complex PETSc native SeqAIJ ILU(0) backend."""
    def __init__(self, K, view_path, *, count=lambda key, n=1: None):
        from petsc4py import PETSc
        if PETSc.ScalarType != np.complex128 or PETSc.COMM_WORLD.getSize() != 1:
            raise ValueError('qualified complex128 MPI1 PETSc required')
        self.count = count; self.calls = 0; self.seconds = 0.
        self.matrix = PETSc.Mat().createAIJ(size=K.shape, csr=(
            K.indptr.astype(PETSc.IntType), K.indices.astype(PETSc.IntType), K.data), comm=PETSc.COMM_SELF)
        self.matrix.assemble()
        self.pc = PETSc.PC().create(PETSc.COMM_SELF)
        self.pc.setOptionsPrefix('task042_v20_fixed_'); self.pc.setOperators(self.matrix)
        self.pc.setType('ilu'); self.pc.setFactorLevels(0)
        self.pc.setFactorOrdering('natural'); self.pc.setFactorShift(PETSc.Mat.FactorShiftType.NONE)
        # No setFromOptions: neither global options nor external -pc_* can
        # override this explicit unique specification or the zero-pivot default.
        self.metadata = dict(specification=SPEC, effective_type=self.pc.getType(),
                             effective_matrix_type=self.matrix.getType(), external_options_applied=False,
                             scalar=str(np.dtype(PETSc.ScalarType)), integer=str(np.dtype(PETSc.IntType)),
                             petsc_version=PETSc.Sys.getVersion(), options_prefix=self.pc.getOptionsPrefix())
        lib = ctypes.CDLL(str(Path(os.environ['PETSC_DIR'])/'lib/libpetsc.so'))
        for name, ctype in [('ZeroPivot',ctypes.c_double),('Levels',ctypes.c_int64 if np.dtype(PETSc.IntType).itemsize==8 else ctypes.c_int),('ShiftType',ctypes.c_int)]:
            value = ctype(); fn = getattr(lib, 'PCFactorGet'+name)
            fn.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctype)]; fn.restype = ctypes.c_int
            if fn(self.pc.handle, ctypes.byref(value)):
                raise RuntimeError('PETSc effective factor getter failed')
            self.metadata['effective_'+name] = value.value
        if self.metadata['effective_Levels'] != 0 or self.metadata['effective_ShiftType'] != 0:
            raise ValueError('fixed native ILU effective levels/shift differ')
        began = perf_counter()
        try:
            self.pc.setUp()
            self.metadata.update(factor_setup_seconds=perf_counter()-began,
                                 factor_mat_info=self.pc.getFactorMatrix().getInfo(),
                                 factor_status='GLOBAL_P3_INCOMPLETE_FACTOR_PRESENT')
        finally:
            viewer = PETSc.Viewer().createASCII(str(view_path), comm=PETSc.COMM_SELF)
            self.pc.view(viewer); viewer.destroy()
        self.x = self.matrix.createVecRight(); self.y = self.matrix.createVecLeft()

    def apply(self, rhs):
        self.count('B0'); began = perf_counter(); self.calls += 1
        if np.shape(rhs) != (self.matrix.getSize()[0],) or not np.isfinite(rhs).all():
            raise ValueError('fixed ILU input inventory/finite failed')
        self.x.array[:] = rhs; self.pc.apply(self.x, self.y)
        result = self.y.array.copy(); self.seconds += perf_counter()-began
        if not np.isfinite(result).all():
            raise ValueError('fixed native ILU nonfinite apply')
        return result

    def destroy(self):
        for name in ('x','y','pc','matrix'):
            if hasattr(self, name):
                getattr(self, name).destroy()


class PortCorrected:
    def __init__(self, body, C, H, F, *, count=lambda key,n=1: None):
        self.body, self.F, self.count = body, F, count
        self.F_seconds=0.;self.F_calls=0
        began = perf_counter()
        self.W = np.column_stack([body.apply(C[:,j]) for j in range(C.shape[1])])
        self.J = H - np.column_stack([self.f(self.W[:,j]) for j in range(C.shape[1])])
        condition = float(np.linalg.cond(self.J))
        if not np.isfinite(condition) or condition > 1e10:
            raise ValueError('P40_NOT_RUN_PORT_CORRECTION_UNSAFE')
        self.factor = lu_factor(self.J); self.small_calls = 0; self.small_seconds = 0.
        rng = np.random.default_rng(422003); r = rng.normal(size=40)+1j*rng.normal(size=40)
        answer = self.solve(r); defect = float(np.linalg.norm(self.J@answer-r)/(np.linalg.norm(self.J)*np.linalg.norm(answer)+np.linalg.norm(r)))
        if defect > 1e-12:
            raise ValueError('P40 small solve operation defect failed')
        self.metadata = dict(cond2=condition, solve_operation_relative=defect,
                             W_payload_bytes=self.W.nbytes, J_sha256=array_hash(self.J),
                             setup_seconds=perf_counter()-began, H_is_Hhat=True, F_is_C_adjoint_assumed=False)

    def f(self, x):
        self.count('F');self.F_calls+=1;began=perf_counter()
        value=self.F(x);self.F_seconds+=perf_counter()-began
        return value

    def solve(self, rhs):
        self.small_calls += 1; began = perf_counter()
        value = lu_solve(self.factor,rhs); self.small_seconds += perf_counter()-began
        return value

    def apply(self, rhs):
        u = self.body.apply(rhs)
        return u + self.W@self.solve(self.f(u))
