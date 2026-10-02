"""Opt-in exact class multiplication; the original packet remains the oracle.

Only local S products change. Shared packet arrays are read-only. No inherited
audit/recovery method can silently verify this backend using itself.
"""
import time
import numpy as np


class ClassBatchAction:
    batch_cells = 64

    def __init__(self, oracle):
        self.oracle = oracle
        self.a = oracle.a
        self.nt, self.np, self.size = oracle.nt, oracle.np, oracle.size
        self.nc, self.lt = oracle.nc, oracle.lt
        if any(v.flags.writeable for v in self.a.values()):
            raise ValueError('class backend requires read-only packet arrays')
        self.groups = tuple((int(k), np.flatnonzero(self.a['classes'] == k))
                            for k in np.unique(self.a['classes']))
        self.conjugates = None
        index_bytes = sum(rows.nbytes for _, rows in self.groups)
        if index_bytes > 32*2**20:
            raise MemoryError('class index cache exceeds 32 MiB')
        if self.a['S'].nbytes + index_bytes <= 32*2**20:
            self.conjugates = self.a['S'].conj()
            self.conjugates.setflags(write=False)
        temporary = (2*64*self.lt+self.lt*self.lt)*16
        if temporary > 64*2**20:
            raise MemoryError('class block workspace exceeds 64 MiB')
        self.metadata = dict(backend='EXACT_CLASS_BATCH64', batch_cells=64,
            cells=self.nc, local_trace=self.lt, classes=len(self.groups),
            persistent_cache_bytes=index_bytes+(0 if self.conjugates is None else self.conjugates.nbytes),
            block_workspace_upper_bytes=temporary,
            old_expanded_S_payload_derived_bytes=16*self.nc*self.lt*self.lt,
            old_payload_is_not_measured_RSS_saving=True, independent_old_oracle=True)
        self.counts = dict(S=0, SH=0)
        self.costs = dict(S=0., SH=0.)

    def apply(self, value, adjoint=False):
        began = time.perf_counter()
        value = np.asarray(value)
        if value.shape != (self.size,) or not np.isfinite(value).all():
            raise ValueError('class action finite vector/shape required')
        trace, port = value[:self.nt], value[self.nt:]
        expanded = self.oracle._expand(trace)
        local = np.empty_like(expanded)
        for k, rows in self.groups:
            S = self.a['S'][k]
            product = (self.conjugates[k] if self.conjugates is not None else S.conj()) if adjoint else S.T
            for start in range(0, len(rows), 64):
                selected = rows[start:start+64]
                local[selected] = expanded[selected] @ product
        if adjoint:
            local -= np.einsum('cpi,p->ci', self.a['Dhat'].conj(), port)
            out_port = np.einsum('cip,ci->p', self.a['Bhat'].conj(), expanded) + self.a['Hhat'].conj().T @ port
            out_trace = self.oracle._pullback(local)
            np.add.at(out_trace, self.a['dr'], -self.a['dv'].conj()*port[self.a['dp']])
            np.add.at(out_port, self.a['bp'], self.a['bv'].conj()*trace[self.a['br']])
        else:
            local += np.einsum('cip,p->ci', self.a['Bhat'], port)
            out_trace = self.oracle._pullback(local) + self.oracle._direct_B(port)
            out_port = (-np.einsum('cpi,ci->p', self.a['Dhat'], expanded)
                        + self.a['Hhat'] @ port - self.oracle._direct_D(trace))
        key = 'SH' if adjoint else 'S'
        self.counts[key] += 1
        self.costs[key] += time.perf_counter()-began
        return np.r_[out_trace, out_port]
