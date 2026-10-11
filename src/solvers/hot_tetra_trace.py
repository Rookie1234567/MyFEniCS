"""Opt-in exact hot reader of sealed assembly-time tetra local packets.

Maps and local classes are checked once. All boundary/interior corrections
are aggregated once; the hot operation forms no global fine K or Schur.
"""
import gc
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import sparse

from .tetra_assembly_packet import LocalTracePacket
from .scattering_anchor_checks import checked_arrays


class HotTracePacket(LocalTracePacket):
    def __init__(self, receipt, *, identity=None, cache_bytes=12*2**30,
                 workspace_bytes=2*2**30, action_limit=600):
        super().__init__(receipt, identity=identity, cache_bytes=cache_bytes)
        self.action_limit = action_limit
        self.workspace_bytes = workspace_bytes
        self.cell_records = []
        groups = defaultdict(list)
        for item in self.manifest['maps']:
            a = checked_arrays(item)
            for j, c in enumerate(a['cells']):
                def part(name):
                    return a[name][a[name+'_offsets'][j]:a[name+'_offsets'][j+1]].copy()
                ids = part('active')
                E = sparse.csr_matrix((part('E_data'), part('E_indices'), part('E_indptr')),
                                     shape=(110, len(ids)))
                key = str(a['class_keys'][j])
                record = (int(c), a['interior'][j].copy(), ids, E, key)
                self.cell_records.append(record)
                groups[key].append(len(self.cell_records)-1)
        self.cell_records.sort(key=lambda r: r[0])
        if [r[0] for r in self.cell_records] != list(range(self.manifest['cells'])):
            raise ValueError('exact packet cell inventory/order')
        # Rebuild grouping after sorting; no cell is omitted or merged by value.
        groups = defaultdict(list)
        for j, r in enumerate(self.cell_records):
            groups[r[4]].append(j)
        self.groups = dict(groups)
        for key in self.groups:
            self.local(key)
        if len(self.cache) != len(self.groups):
            raise MemoryError('hot cache cannot keep all exact classes')
        self.single_maps = []
        for _, _, ids, E, _ in self.cell_records:
            self.single_maps.append((ids[E.indices], E.data.copy())
                                    if np.all(np.diff(E.indptr) == 1) else None)
        self.calls.update(map_reads=len(self.manifest['maps']), map_hot_reads=0,
                          scatter_add=0, class_hot_hits=0, boundary_aggregate=0)
        self.actual_interior_port_cells = []
        self.Ctilde = self.C[self.retained[:self.nt]].tocsr()
        self.Dtilde = -self.DT[self.retained[:self.nt]].T.tocsr()
        self.Htilde = np.diag(self.H.astype(np.complex128))
        # No assumption that D=C^H or that tiny interior support is zero.
        cr, cc, cv, dr, dc, dv = [], [], [], [], [], []
        payload = 0

        def flush():
            nonlocal payload
            if cv:
                self.Ctilde += sparse.csr_matrix((np.concatenate(cv),
                    (np.concatenate(cr), np.concatenate(cc))), shape=(self.nt, self.m))
                self.Dtilde += sparse.csr_matrix((np.concatenate(dv),
                    (np.concatenate(dr), np.concatenate(dc))), shape=(self.m, self.nt))
            for items in (cr, cc, cv, dr, dc, dv):
                items.clear()
            payload = 0

        for c, i, ids, E, key in self.cell_records:
            ports, Ci, Di = self._interior_ports(i)
            if not len(ports):
                continue
            self.actual_interior_port_cells.append(c)
            a = self.cache[key]
            vi = self.solve_local(a, a['it'])
            vc = self.solve_local(a, Ci)
            ccor = np.asarray(-E.conj().T @ (a['ti'] @ vc))
            dcor = np.asarray((Di @ vi) @ E)
            self.Htilde[np.ix_(ports, ports)] += Di @ vc
            # Keep exact stored algebra, including structural/numerical zeros.
            rr = np.repeat(ids, len(ports)); pp = np.tile(ports, len(ids))
            cr.append(rr); cc.append(pp); cv.append(ccor.ravel())
            dr.append(pp); dc.append(rr); dv.append(dcor.T.ravel())
            payload += ccor.nbytes + dcor.nbytes + rr.nbytes*2 + pp.nbytes*2
            if payload > min(workspace_bytes//4, 128*2**20):
                flush()
        flush()
        self.Ctilde.sum_duplicates(); self.Dtilde.sum_duplicates()
        self.calls['boundary_aggregate'] = 1
        maps = sum(i.nbytes+ids.nbytes+E.data.nbytes+E.indices.nbytes+E.indptr.nbytes
                   for _, i, ids, E, _ in self.cell_records)
        single = sum(sum(x.nbytes for x in r) for r in self.single_maps if r is not None)
        boundary = sum(A.data.nbytes+A.indices.nbytes+A.indptr.nbytes
                       for A in (self.Ctilde, self.Dtilde))+self.Htilde.nbytes
        self.hot_cache_bytes = self.live_cache_bytes+maps+single+boundary
        if self.hot_cache_bytes > cache_bytes:
            raise MemoryError('exact class/map/boundary aggregate exceeds hot cache')
        paths = [self.root/'manifest.json', self.root/'COMMIT']
        paths += [self.root/r['file'] for r in self.manifest['members'].values()]
        paths += [Path(r['path']) for r in self.manifest['classes'].values()]
        paths += [Path(r['path']) for r in self.manifest['maps']]
        self.file_signatures = {p:self.signature(p) for p in paths}
        for arrays in self.cache.values():
            for array in arrays.values():array.setflags(write=False)

    @staticmethod
    def signature(path):
        s=path.stat()
        return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns

    def require_frozen(self):
        # The initial hashes are authoritative. A mutation invalidates the
        # checked reader; hot calls do not repeatedly hash four GiB of data.
        for path,signature in self.file_signatures.items():
            if self.signature(path)!=signature:
                raise ValueError('frozen local packet file changed: '+str(path))

    def identity_operation_scale(self,t,full,rhs):
        """Absolute operation bound, separate from the physical RHS scale."""
        scale=np.abs(rhs).copy()
        scale[:self.n]+=abs(self.C)@np.abs(full[self.n:])
        scale[self.n:]+=abs(self.DT.T)@np.abs(full[:self.n])+np.abs(self.H*full[self.n:])
        for _,i,ids,E,key in self.cell_records:
            a=self.cache[key];v=E@t[ids];xi=full[i]
            vi=self.solve_local(a,a['it']@v)
            raw_trace_bound=abs(a['schur'])@abs(v)+abs(a['ti'])@(abs(xi)+abs(vi))
            np.add.at(scale,self.retained[ids],abs(E).T@raw_trace_bound)
            scale[i]+=abs(a['ii'])@abs(xi)+abs(a['it'])@abs(v)
        return float(np.linalg.norm(scale))

    def cells(self):
        if not hasattr(self, 'cell_records'):
            yield from super().cells()
            return
        for c, i, ids, E, key in self.cell_records:
            yield c, i, ids, E, self.local(key)

    def apply_trace(self, t):
        self.require_frozen()
        t = np.asarray(t)
        if t.shape != (len(self.retained),) or not np.isfinite(t).all():
            raise ValueError('finite hot retained vector length')
        if self.calls['trace_action'] >= self.action_limit:
            raise RuntimeError('whole-interface action budget exhausted')
        self.calls['trace_action'] += 1
        out = np.empty_like(t)
        out[:self.nt] = self.Ctilde @ t[self.nt:]
        out[self.nt:] = self.Dtilde @ t[:self.nt]+self.Htilde @ t[self.nt:]
        self.calls['boundary_C'] += 1; self.calls['boundary_D'] += 1
        for key, members in self.groups.items():
            a = self.cache[key]
            for first in range(0, len(members), 64):
                batch = members[first:first+64]
                v = np.empty((110, len(batch)), np.complex128)
                for j, idx in enumerate(batch):
                    r = self.single_maps[idx]
                    if r is None:
                        _, _, ids, E, _ = self.cell_records[idx]
                        v[:, j] = E @ t[ids]
                    else:
                        ids, coef = r; v[:, j] = coef*t[ids]
                y = a['schur'] @ v
                for j, idx in enumerate(batch):
                    r = self.single_maps[idx]
                    if r is None:
                        _, _, ids, E, _ = self.cell_records[idx]
                        np.add.at(out, ids, E.conj().T @ y[:, j])
                    else:
                        ids, coef = r
                        np.add.at(out, ids, np.conj(coef)*y[:, j])
                self.calls['scatter_add'] += len(batch)
                self.calls['class_hot_hits'] += 1
        return out

    def release_hot(self):
        self.cell_records.clear(); self.groups.clear(); self.single_maps.clear()
        self.Ctilde = self.Dtilde = self.Htilde = None
        self.release_cache(); gc.collect()
