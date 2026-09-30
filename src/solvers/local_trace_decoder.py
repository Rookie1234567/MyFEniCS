"""Matched block trace decoders and a bounded complementary global space."""

import numpy as np


class BlockTraceDecoder:
    def __init__(self, rows, blocks, full_rows):
        self.rows = [np.asarray(r, np.int64) for r in rows]
        self.blocks = [np.asarray(q, np.complex128) for q in blocks]
        joined = np.concatenate(self.rows)
        if len(joined) != full_rows or not np.array_equal(np.sort(joined), np.arange(full_rows)):
            raise ValueError('local decoder has missing/duplicate canonical rows')
        if any(q.shape[0] != len(r) or q.shape[1] == 0 for r,q in zip(self.rows,self.blocks,strict=True)):
            raise ValueError('empty local support or numerical rank')
        self.offsets = np.r_[0,np.cumsum([q.shape[1] for q in self.blocks])]
        self.shape = (full_rows, int(self.offsets[-1]))
        self.dtype = np.dtype(np.complex128)
        self.nbytes = sum(q.nbytes+r.nbytes for r,q in zip(self.rows,self.blocks,strict=True))

    def __matmul__(self, coefficients):
        c = np.asarray(coefficients, complex)
        if c.ndim not in (1,2) or c.shape[0] != self.shape[1]:
            raise ValueError('block coefficient inventory')
        out = np.zeros((self.shape[0],)+c.shape[1:], complex)
        for j,(rows,Q) in enumerate(zip(self.rows,self.blocks,strict=True)):
            out[rows] = Q @ c[self.offsets[j]:self.offsets[j+1]]
        return out

    def adjoint(self, trace):
        value = np.asarray(trace, complex)
        if value.shape[0] != self.shape[0]:
            raise ValueError('block trace inventory')
        return np.concatenate([Q.conj().T @ value[r] for r,Q in zip(self.rows,self.blocks,strict=True)])

    def column(self, index):
        j = int(np.searchsorted(self.offsets, index, side='right')-1)
        if not 0 <= index < self.shape[1]:
            raise IndexError(index)
        result = np.zeros(self.shape[0], complex)
        result[self.rows[j]] = self.blocks[j][:, index-self.offsets[j]]
        return result

    def __getitem__(self, key):
        if key[0] != slice(None) or not isinstance(key[1],(int,np.integer)):
            raise ValueError('only one explicit full canonical column is allowed')
        return self.column(int(key[1]))

    def orthogonality(self):
        norm2 = 0.
        for q in self.blocks:
            gram = q.conj().T@q-np.eye(q.shape[1])
            norm2 += np.linalg.norm(gram)**2
        return float(np.sqrt(norm2/self.shape[1]))

    def identity_checks(self, seed=421502):
        rng = np.random.default_rng(seed)
        c = rng.standard_normal(self.shape[1])+1j*rng.standard_normal(self.shape[1])
        d = rng.standard_normal(self.shape[0])+1j*rng.standard_normal(self.shape[0])
        # This witness evaluates the explicit injection patch by patch.  No
        # all-zero 18144-by-1560 matrix is retained in the deployed decoder.
        forward = np.zeros(self.shape[0], complex)
        for j,(r,q) in enumerate(zip(self.rows,self.blocks,strict=True)):
            forward += np.bincount(r,weights=(q@c[self.offsets[j]:self.offsets[j+1]]).real,minlength=self.shape[0])
            forward += 1j*np.bincount(r,weights=(q@c[self.offsets[j]:self.offsets[j+1]]).imag,minlength=self.shape[0])
        actual = self@c
        lhs,rhs = np.vdot(d,actual),np.vdot(self.adjoint(d),c)
        return dict(forward_relative=float(np.linalg.norm(actual-forward)/np.linalg.norm(forward)),
                    adjoint_operation_relative=float(abs(lhs-rhs)/(np.linalg.norm(d)*np.linalg.norm(actual))),
                    orthogonality=self.orthogonality(), payload_bytes=self.nbytes,
                    explicitly_assembled_dense_zero_decoder=False)


def matched_local_spaces(libraries, rows, full_rows, count=lambda *a:None):
    from scipy.linalg import svd
    left, ranks, records = {}, {}, {}
    for family in ('POLY','NN'):
        left[family], ranks[family], records[family] = [],[],[]
        for patch, matrix in enumerate(libraries[family]):
            if matrix.shape != (len(rows[patch]),195) or not np.isfinite(matrix).all():
                raise ValueError('reviewed local raw library differs')
            norms = np.linalg.norm(matrix,axis=0)
            nonzero = norms > 0
            if not np.isfinite(norms).all() or not nonzero.any():
                raise ValueError('zero or nonfinite local library')
            count('local_SVD')
            U,singular,_ = svd(matrix[:,nonzero]/norms[nonzero],full_matrices=False,
                              lapack_driver='gesdd',check_finite=False)
            rank = int(np.count_nonzero(singular > 1e-12*singular[0]))
            left[family].append(U);ranks[family].append(rank)
            records[family].append(dict(patch=patch,rank=rank,nominal_columns=195,
                zero_columns=np.flatnonzero(~nonzero).tolist(),column_norms=norms,
                singular_values=singular,threshold=1e-12,driver='gesdd'))
    common = np.minimum(ranks['POLY'],ranks['NN'])
    if np.any(common==0):
        raise ValueError('ZERO_MATCHED_PATCH_RANK')
    decoders = {family:BlockTraceDecoder(rows,[u[:,:r].copy(order='F')
                for u,r in zip(left[family],common,strict=True)],full_rows) for family in left}
    return decoders,dict(common_rank_by_patch=common,actual_columns=int(sum(common)),
                         original_rank_by_family=ranks,library_records=records,
                         rank_padding=False,rank_threshold_scanned=False)


class UnionTraceDecoder:
    def __init__(self, global_Q, complement):
        self.G,self.U = global_Q,complement
        if self.G.shape[0]!=self.U.shape[0]:raise ValueError('union canonical row mismatch')
        self.shape=(self.G.shape[0],self.G.shape[1]+self.U.shape[1])
        self.dtype=np.dtype(np.complex128)
        self.nbytes=self.G.nbytes+self.U.nbytes

    def __matmul__(self,c):
        return self.G@c[:self.G.shape[1]]+self.U@c[self.G.shape[1]:]

    def adjoint(self,t):
        return np.concatenate((self.G.conj().T@t,self.U.conj().T@t))

    def column(self,j):
        return self.G[:,j] if j<self.G.shape[1] else self.U[:,j-self.G.shape[1]]

    def __getitem__(self,key):
        if key[0]!=slice(None):raise ValueError('full canonical column required')
        return self.column(key[1])

    def orthogonality(self):
        gg=self.G.conj().T@self.G-np.eye(self.G.shape[1])
        uu=self.U.conj().T@self.U-np.eye(self.U.shape[1])
        gu=self.G.conj().T@self.U
        return float(np.sqrt((np.linalg.norm(gg)**2+np.linalg.norm(uu)**2+2*np.linalg.norm(gu)**2)/self.shape[1]))


def complementary_space(global_Q, local, count=lambda *a:None, heartbeat=lambda *a,**k:None):
    from scipy.linalg import qr,svd
    Y=np.empty(local.shape,dtype=np.complex128,order='F')
    for j in range(0,local.shape[1],32):
        stop=min(j+32,local.shape[1])
        block=np.column_stack([local.column(k) for k in range(j,stop)])
        Y[:,j:stop]=block-global_Q@(global_Q.conj().T@block)
        heartbeat('union_project',completed=stop,total=local.shape[1])
    count('complement_SVD')
    U,singular,_=svd(Y,full_matrices=False,lapack_driver='gesdd',check_finite=False)
    q=int(np.count_nonzero(singular>1e-10))
    del Y
    if q==0:return np.empty((global_Q.shape[0],0),complex),dict(raw_q=0,singular_values=singular)
    # One reorthogonalization against the preserved G0; economic QR only
    # stabilizes these retained directions, without changing the rank rule.
    U=U[:,:q].copy(order='F')
    for j in range(0,q,32):
        stop=min(j+32,q)
        U[:,j:stop]-=global_Q@(global_Q.conj().T@U[:,j:stop])
    U,_=qr(U,mode='economic',pivoting=False,check_finite=False)
    return U,dict(raw_q=q,singular_values=singular,absolute_threshold=1e-10,
                  projection_block_columns=32,reorthogonalizations=1,
                  full_square_projection_constructed=False,global_Q_preserved=True)
