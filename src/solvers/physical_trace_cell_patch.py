"""Exact-class cell-joint inverse in the existing high-trace coefficient space."""
import hashlib
import json
from time import perf_counter
import numpy as np
from scipy.linalg import lu_solve


def signature_array(digest, value):
    value = np.asarray(value)
    metadata = json.dumps(dict(shape=list(value.shape), dtype=value.dtype.str,
        order='C', nbytes=value.nbytes), sort_keys=True).encode()
    digest.update(len(metadata).to_bytes(8, 'big')); digest.update(metadata)
    raw = value.tobytes(order='C')
    digest.update(len(raw).to_bytes(8, 'big')); digest.update(raw)


def row_complete_patch(parts, ports, dimension):
    """Unweighted D, in the independently audited accumulation order."""
    D = np.zeros((dimension, dimension), complex)
    for schur, injection in parts:
        D += injection.conj().T @ schur @ injection
    for coupling, projection, normalization in ports:
        D += np.outer(coupling, projection) / normalization
    return D


def symmetric_patch_solve(rhs, indices, weights, groups, *, check, sample):
    """Both multiplicity weights stay outside each unweighted local inverse."""
    result = np.zeros_like(rhs)
    worst = 0.; logical = 0; sample_count = 0; sample_seconds = 0.
    for index,group in enumerate(groups):
        if index%8 == 0:
            started = perf_counter(); sample(); sample_seconds += perf_counter()-started; sample_count += 1
        rows = indices[group['members']]
        local_rhs = (weights[rows] * rhs[rows]).T
        z = lu_solve(group['factor'], local_rhs)
        image = group['D'] @ z
        # Per RHS, not a batch norm which could conceal one inaccurate column.
        denominator = np.linalg.norm(image, axis=0) + np.linalg.norm(local_rhs, axis=0)
        errors = np.linalg.norm(image-local_rhs, axis=0) / np.maximum(denominator, np.finfo(float).tiny)
        defect = float(np.max(errors)); check(defect)
        worst = max(worst, defect); logical += len(rows)
        np.add.at(result, rows.ravel(), (weights[rows] * z.T).ravel())
    started = perf_counter(); sample(); sample_seconds += perf_counter()-started; sample_count += 1
    return result, dict(logical_rhs=logical, local_residual_max=worst, class_batches=len(groups),
        resource_samples=sample_count, resource_sample_seconds=sample_seconds)


def build_cell_joint_patch_maps(cells, entities, blocks):
    """Build only current cell/entity coefficient maps and PoU weights."""
    offsets = np.cumsum([0] + [block['J'].shape[1] for block in blocks])
    patches = [[] for _ in cells]
    for index, entity in enumerate(entities):
        for cell in entity['support_cells']:
            patches[cell].append(index)
    indices = np.asarray([
        np.concatenate([np.arange(offsets[index], offsets[index + 1]) for index in patch])
        for patch in patches
    ], dtype=np.int64)
    if indices.shape != (252, 144):
        raise ValueError('frozen patch dimensions changed')
    multiplicity = np.bincount(indices.ravel(), minlength=int(offsets[-1]))
    if np.any(multiplicity == 0):
        raise ValueError('patch coefficient coverage failed')
    return offsets, patches, indices, 1. / np.sqrt(multiplicity)


class CellJointTraceInverse:
    """84 D/LU pairs; patch maps and topology weights, no dense F or global D."""
    def __init__(self, mapping, cells, entities, blocks, schurs, carrier, authority,
                 *, sample, save, marker):
        from .physical_trace_entity import checked_lu
        self.groups = []; self.counts = dict(patch_LU=0, patch_setup_rhs=0,
            patch_apply_rhs=0, patch_class_batches=0, applications=0,resource_samples=0,resource_sample_seconds=0.)
        self.offsets, patches, self.indices, self.weights = build_cell_joint_patch_maps(
            cells, entities, blocks)
        multiplicity = np.rint(1. / self.weights**2).astype(np.int64)
        self.class_ids = np.empty(len(cells), dtype=np.int64)
        slaves = set(map(int, mapping['slaves'])); cache = {}
        def injection(cell, lookup):
            B = np.zeros((192,144), complex)
            for j,row in enumerate(mapping['dofmap'][cell][:192]):
                if int(row) not in slaves: links = [(int(row),1.+0j)]
                else:
                    a,b = mapping['offsets'][row:row+2]
                    links = zip(mapping['masters'][a:b], mapping['coefficients'][a:b])
                for target,phase in links:
                    if phase != 0 and int(target) in lookup:
                        columns,values = lookup[int(target)]; B[j,columns] += phase*values
            return B
        for cell,patch in enumerate(patches):
            sample(); lookup = {}; offset = 0
            for index in patch:
                block = blocks[index]; dimension = block['J'].shape[1]
                for row,values in zip(block['rows'],block['J']):
                    if int(row) in lookup: raise ValueError('overlapping entity coefficient maps')
                    lookup[int(row)] = (slice(offset,offset+dimension),values)
                offset += dimension
            supports = sorted({c for index in patch for c in entities[index]['support_cells']})
            digest = hashlib.sha256(); digest.update(b'cell_patch_exact_signature_v1')
            digest.update(len(supports).to_bytes(8,'big'))
            for other in supports:
                key = cells[other].encode(); digest.update(len(key).to_bytes(8,'big')); digest.update(key)
                signature_array(digest,injection(other,lookup))
            ports = []; digest.update(len(carrier.entries).to_bytes(8,'big'))
            for entry in carrier.entries:
                c = np.zeros(144,complex); p = c.copy()
                for row,value in zip(entry.coupling_rows,entry.coupling_values):
                    if int(row) in lookup:
                        columns,values = lookup[int(row)]; c[columns] += values.conj()*value
                for row,value in zip(entry.projection_rows,entry.projection_values):
                    if int(row) in lookup:
                        columns,values = lookup[int(row)]; p[columns] += value*values
                h = entry.normalization_h
                mode = json.dumps(entry.mode_key,separators=(',',':')).encode()
                digest.update(len(mode).to_bytes(8,'big')); digest.update(mode)
                for value in (c,p,np.asarray(h)): signature_array(digest,value)
                ports.append((c,p,h))
            signature = digest.hexdigest(); expected = authority['cells'][cell]
            if expected['cell'] != cell or signature != expected['signature_sha256']:
                raise ValueError('patch exact construction authority mismatch')
            if signature not in cache:
                if len(cache) >= 84: raise ValueError('patch exact class cap')
                D = row_complete_patch(((schurs[cells[c]],injection(c,lookup)) for c in supports),ports,144)
                matrix_hash = hashlib.sha256(D.tobytes()).hexdigest()
                if matrix_hash != expected['matrix_sha256']: raise ValueError('patch D byte authority mismatch')
                factor,defect = checked_lu(D); self.counts['patch_LU'] += 1
                witness = np.arange(1,145)+1j; rhs = D@witness; z = lu_solve(factor,rhs)
                residual = float(np.linalg.norm(D@z-rhs)/(np.linalg.norm(D@z)+np.linalg.norm(rhs)))
                self.counts['patch_setup_rhs'] += 1
                class_id = len(self.groups); cache[signature] = class_id
                save(f'trace_patch_class_{class_id:03d}',dict(D=D,LU=factor[0],pivots=factor[1],
                    signature_sha256=signature,matrix_sha256=matrix_hash,representative_cell=cell,
                    factor_relative=defect,test_rhs=rhs,test_solution=z,test_relative=residual))
                self._check(residual)
                self.groups.append(dict(D=D,factor=factor,members=[]))
            class_id = cache[signature]
            if class_id != expected['class_id']: raise ValueError('patch class ordering mismatch')
            self.class_ids[cell] = class_id; self.groups[class_id]['members'].append(cell)
            if cell%32 == 0: marker('joint_patch_setup',dict(cell=cell,classes=len(cache)))
        if len(cache) != 84: raise ValueError('patch exact class inventory differs')
        for group in self.groups: group['members'] = np.asarray(group['members'],dtype=np.int64)
        map_bytes=sum(a.nbytes for a in (self.indices,self.weights,self.offsets,self.class_ids))+sum(g['members'].nbytes for g in self.groups)
        if map_bytes>444056:raise MemoryError('joint coefficient map reserve exceeded')
        save('trace_patch_storage',dict(map_bytes=map_bytes,map_reserved_bytes=444056,
            D_bytes=sum(g['D'].nbytes for g in self.groups),
            LU_pivot_bytes=sum(sum(a.nbytes for a in g['factor']) for g in self.groups),
            map_components=dict(indices=self.indices.nbytes,weights=self.weights.nbytes,offsets=self.offsets.nbytes,
                class_ids=self.class_ids.nbytes,members=sum(g['members'].nbytes for g in self.groups))))
        save('trace_patch_maps',dict(indices=self.indices,weights=self.weights,offsets=self.offsets,
            class_ids=self.class_ids,multiplicity=multiplicity,counts=self.counts))

    @staticmethod
    def _check(defect):
        if not np.isfinite(defect) or defect > 1e-11:
            raise ValueError(f'patch actual D residual failed: defect={defect!r}, limit=1e-11')

    def apply(self, coefficients, sample):
        rhs = np.concatenate(coefficients)
        result,facts = symmetric_patch_solve(rhs,self.indices,self.weights,self.groups,
            check=self._check,sample=sample)
        self.counts['applications'] += 1
        self.counts['patch_apply_rhs'] += facts['logical_rhs']
        self.counts['patch_class_batches'] += facts['class_batches']
        self.counts['resource_samples'] = self.counts.get('resource_samples',0)+facts['resource_samples']
        self.counts['resource_sample_seconds'] = self.counts.get('resource_sample_seconds',0.)+facts['resource_sample_seconds']
        self.last_facts = facts
        return [result[a:b] for a,b in zip(self.offsets[:-1],self.offsets[1:])]

    def storage(self):
        return [self.indices,self.weights,self.offsets,self.class_ids,self.groups]

    def destroy(self):
        """Release the temporary exact-joint inverse after route replacement."""
        self.groups.clear()
        self.indices = np.empty((0, 0), dtype=np.int64)
        self.weights = np.empty(0, dtype=float)
        self.offsets = np.empty(0, dtype=np.int64)
        self.class_ids = np.empty(0, dtype=np.int64)
        self.counts.clear()
