"""MPI1 three-column joint MR workspace; no physical operator or new inverse."""
import time

import numpy as np
from scipy.linalg import norm
from scipy.linalg.blas import zgemv
from scipy.linalg.lapack import zgeqrf, zungqr

CUTOFF = 1e-12
MAX_BYTES = 64*1024**2


def array_view(vector):
    return vector.getArray(readonly=True) if hasattr(vector, 'getArray') else np.asarray(vector)


class JointMR3:
    """Retain only this PC's D/W. LAPACK workspace is explicitly bounded."""
    def __init__(self, rhs):
        if hasattr(rhs, 'getComm') and rhs.getComm().getSize() != 1:
            raise ValueError('joint MR3 currently requires MPI1; no gather')
        q = array_view(rhs)
        if q.ndim != 1 or q.dtype != np.complex128 or not np.all(np.isfinite(q)):
            raise ValueError('joint MR input must be finite complex128')
        # D/W=6 columns; conservative allowance includes QR copies/Q/candidate,
        # verification Vecs, boolean masks and bounded small LAPACK workspace.
        self.payload_limit = 16*q.nbytes+65536
        if self.payload_limit > MAX_BYTES:
            raise ValueError('joint MR3 additional workspace exceeds 64MiB')
        self.d = np.zeros((q.size,3), dtype=np.complex128, order='F')
        self.w = np.zeros_like(self.d, order='F')
        self.count = 0

    def capture(self, direction, applied):
        if self.count >= 3:
            raise ValueError('joint MR3 accepts only the existing three directions')
        d = array_view(direction)
        w = np.zeros(d.size, dtype=np.complex128) if applied is None else array_view(applied)
        if d.shape != self.d[:,0].shape or w.shape != d.shape or not (np.all(np.isfinite(d)) and np.all(np.isfinite(w))):
            raise RuntimeError('nonfinite or incompatible physical direction/action')
        self.d[:,self.count] = d
        self.w[:,self.count] = w
        self.count += 1

    def candidate(self, rhs):
        started = time.perf_counter()
        q = array_view(rhs)
        if not np.all(np.isfinite(q)):
            raise RuntimeError('nonfinite physical RHS cannot be hidden by fallback')
        facts = dict(cutoff=CUTOFF, rank=0, normalized_singular_values=[],
            coefficients=[], normalized_coefficients=[], fallback=False, fallback_reason=None,
            extra_A6_count=0, extra_A6_seconds=0., workspace_bound_bytes=self.payload_limit,
            captured_columns=self.count, retained_DW_bytes=self.d.nbytes+self.w.nbytes,
            lapack_lwork_complex=9)
        scales = np.array([norm(self.w[:,i]) for i in range(3)])
        facts['action_norms'] = scales.tolist()
        facts['direction_norms'] = [float(norm(self.d[:,i])) for i in range(3)]
        if not (np.all(np.isfinite(scales)) and np.all(np.isfinite(facts['direction_norms']))):
            raise RuntimeError('nonfinite physical direction/action norm')
        try:
            for i,s in enumerate(scales):
                if s == 0:
                    self.d[:,i] = 0; self.w[:,i] = 0
                else:
                    self.d[:,i] /= s; self.w[:,i] /= s
            if not (np.all(np.isfinite(self.d)) and np.all(np.isfinite(self.w))):
                facts.update(fallback=True, fallback_reason='nonfinite_scaled_candidate_columns')
                return None, facts
            if not np.any(scales):
                return np.zeros_like(q), facts
            # Fixed minimum-sized work arrays; no N-by-N object or normal equations.
            qr,tau,work,info = zgeqrf(self.w, lwork=9, overwrite_a=True)
            if info: raise RuntimeError(f'joint QR failed with LAPACK info={info}')
            k = min(q.size,3)
            r = np.triu(qr[:k,:]).copy()
            basis,work,info = zungqr(qr[:,:k], tau, lwork=9, overwrite_a=True)
            if info: raise RuntimeError(f'joint Q failed with LAPACK info={info}')
            facts['QR_shares_W'] = bool(np.shares_memory(qr,self.w))
            facts['Q_shares_QR'] = bool(np.shares_memory(basis,qr))
            # Complex conjugate transpose without an N-by-3 conjugation copy.
            projected = zgemv(1., basis, q, trans=2)
            u,s,vh = np.linalg.svd(r, full_matrices=False)
            keep = s > CUTOFF*s[0]
            facts['rank'] = int(np.count_nonzero(keep))
            facts['normalized_singular_values'] = (s/s[0]).tolist()
            coefficients = vh[keep,:].conj().T @ ((u[:,keep].conj().T @ projected)/s[keep])
            raw = np.divide(coefficients,scales,out=np.zeros(3,dtype=complex),where=scales!=0)
            if not (np.all(np.isfinite(coefficients)) and np.all(np.isfinite(raw))):
                facts.update(fallback=True, fallback_reason='nonfinite_joint_coefficients')
                return None, facts
            facts['normalized_coefficients'] = [[float(x.real),float(x.imag)] for x in coefficients]
            facts['coefficients'] = [[float(x.real),float(x.imag)] for x in raw]
            candidate = self.d @ coefficients
            if not np.all(np.isfinite(candidate)):
                facts.update(fallback=True, fallback_reason='nonfinite_joint_candidate')
                return None, facts
            return candidate, facts
        except np.linalg.LinAlgError:
            facts.update(fallback=True, fallback_reason='small_SVD_failed')
            return None, facts
        finally:
            facts['QR_seconds'] = time.perf_counter()-started

    def close(self):
        self.d = self.w = None
