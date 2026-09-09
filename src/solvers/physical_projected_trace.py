"""Column-bounded non-Hermitian trace Schur oracle; no outer PC or FE assembly."""
import hashlib
from time import perf_counter
import numpy as np
from scipy.linalg import lu_solve
from scipy.sparse import csr_matrix
from .physical_bubble_particular import expand_primal
from .condensed_fine_reference import project_unconstrained_mpc_dual
from .physical_trace_entity import checked_lu, relative_defect


class ProjectedPatchCross:
    """Stream P^H S_Q J and J^H S_Q P; never assume the two are adjoints."""
    def __init__(self, mapping, coarse_mapping, cells, classes, blocks, entity_ids,
                 fine_ports, coarse_ports, *, sample=lambda: None, save=lambda name, row: None):
        self.mapping, self.coarse_mapping = mapping, coarse_mapping
        self.classes, self.sample = classes, sample
        self.save = save
        self.coarse_rows = len(coarse_mapping['offsets'])-1
        self.dimension = sum(blocks[i]['J'].shape[1] for i in entity_ids)
        self.offsets = np.cumsum([0]+[blocks[i]['J'].shape[1] for i in entity_ids])
        lookup = {}
        for offset, eid in zip(self.offsets[:-1], entity_ids, strict=True):
            block = blocks[eid]
            for row, values in zip(block['rows'], block['J'], strict=True):
                if int(row) in lookup: raise ValueError('overlapping patch entity rows')
                lookup[int(row)] = (offset+np.arange(len(values)), values)
        slaves = set(map(int, mapping['slaves']))
        self.local = []
        for cell, key in enumerate(cells):
            rr, cc, vv = [], [], []
            for local_row, row in enumerate(mapping['dofmap'][cell]):
                if int(row) in slaves:
                    a, b = mapping['offsets'][row:row+2]
                    links = zip(mapping['masters'][a:b], mapping['coefficients'][a:b])
                else: links = [(int(row), 1.+0j)]
                for target, phase in links:
                    if phase and int(target) in lookup:
                        columns, values = lookup[int(target)]
                        rr.extend([local_row]*len(columns));cc.extend(columns);vv.extend(phase*values)
            if vv:
                J = csr_matrix((vv, (rr, cc)), shape=(len(mapping['dofmap'][cell]), self.dimension))
                J.sum_duplicates();J.eliminate_zeros()
                self.local.append((cell, key, J))
        if len(fine_ports) != len(coarse_ports): raise ValueError('carrier lengths differ')
        self.ports = []
        for fine, coarse in zip(fine_ports, coarse_ports, strict=True):
            if fine['mode_key'] != coarse['mode_key'] or fine['normalization_h'] != coarse['normalization_h']:
                raise ValueError('ordered physical modes differ')
            left = np.zeros(self.dimension, complex);right = left.copy()
            for row, value in zip(fine['coupling_rows'], fine['coupling_values'], strict=True):
                if int(row) in lookup:
                    columns, values = lookup[int(row)];left[columns] += values.conj()*value
            for row, value in zip(fine['projection_rows'], fine['projection_values'], strict=True):
                if int(row) in lookup:
                    columns, values = lookup[int(row)];right[columns] += value*values
            self.ports.append((left, right, coarse))
        self.seconds = dict(R=0., L=0.)
        self.saved_Q_rhs = 0

    def right(self, first, stop):
        """At most eight columns of R, with full row/MPC and modal accumulation."""
        if not 0 <= first < stop <= self.dimension or stop-first > 8:
            raise ValueError('R column block must be between one and eight')
        started = perf_counter();out = np.zeros((self.coarse_rows, stop-first), complex)
        per_column = np.zeros(stop-first);worst_cell = np.full(stop-first, -1, dtype=int)
        for cell, key, injection in self.local:
            self.sample();h = self.classes[key];A, Q = h['A'], h['Q']
            local = injection[:, first:stop].toarray();aj = A@local;rhs = Q.conj().T@aj
            z = lu_solve(h['factor'], rhs);self.saved_Q_rhs += stop-first
            image = h['D']@z;denominator = np.linalg.norm(image, axis=0)+np.linalg.norm(rhs, axis=0)
            errors = np.divide(np.linalg.norm(image-rhs, axis=0), denominator,
                out=np.zeros(stop-first), where=denominator != 0)
            replace = errors > per_column;per_column[replace] = errors[replace];worst_cell[replace] = cell
            if not np.isfinite(errors).all() or np.max(errors) > 1e-11:
                self.save(f'Q_failure_{first:03d}_{cell}', dict(first=first, cell=cell, rhs=rhs, solution=z,
                    applied=image, per_column_relative=errors, limit=1e-11))
                raise ValueError('saved Q per-column solve gate')
            value = h['P'].conj().T@(aj-A@(Q@z))
            np.add.at(out, self.coarse_mapping['dofmap'][cell], value)
        for j in range(stop-first):out[:, j] = project_unconstrained_mpc_dual(out[:, j], self.coarse_mapping)
        for _, projection, coarse in self.ports:
            np.add.at(out, coarse['coupling_rows'], np.outer(coarse['coupling_values'], projection[first:stop])/coarse['normalization_h'])
        self.seconds['R'] += perf_counter()-started
        worst = int(np.argmax(per_column))
        self.right_facts = dict(worst_relative=float(per_column[worst]), column=first+worst,
            cell=int(worst_cell[worst]), per_column_relative=per_column.copy(), limit=1e-11)
        return out

    def left(self, values):
        """L times <=8 coarse columns; W supplies the already condensed P."""
        if values.ndim != 2 or values.shape[0] != self.coarse_rows or not 1 <= values.shape[1] <= 8:
            raise ValueError('L input must contain one to eight coarse columns')
        started = perf_counter();expanded = np.column_stack([expand_primal(v, self.coarse_mapping) for v in values.T])
        out = np.zeros((self.dimension, values.shape[1]), complex)
        for cell, key, injection in self.local:
            self.sample();h = self.classes[key]
            out += injection.conj().T@(h['A']@(h['W']@expanded[self.coarse_mapping['dofmap'][cell]]))
        for coupling, _, coarse in self.ports:
            amplitude = coarse['projection_values']@values[coarse['projection_rows']]/coarse['normalization_h']
            out += np.outer(coupling, amplitude)
        self.seconds['L'] += perf_counter()-started
        return out

    def retained_bytes(self):
        return int(self.offsets.nbytes+sum(J.data.nbytes+J.indices.nbytes+J.indptr.nbytes for _, _, J in self.local)
                   +sum(left.nbytes+right.nbytes for left, right, _ in self.ports))


def projected_local_oracle(cross, original_D, solve_one, *, save, sample=lambda: None):
    """Exactly dimension logical S solves; persist every block and any failed RHS."""
    dimension = cross.dimension
    if original_D.shape != (dimension, dimension): raise ValueError('patch D shape differs')
    effective = original_D.copy();Rc = np.zeros(cross.coarse_rows, complex)
    c = np.arange(1, dimension+1)+1j;started = perf_counter();logical = 0
    for first in range(0, dimension, 8):
        stop = min(first+8, dimension);sample();R = cross.right(first, stop);X = np.empty_like(R);facts = []
        for j in range(stop-first):
            try:
                value, row = solve_one(R[:, j].copy());logical += 1
                if not np.isfinite(value).all() or not np.isfinite(row['relative']) or row['relative'] > 1e-10:
                    raise ValueError('S column did not pass native true residual')
                X[:, j] = value;facts.append(row)
            except BaseException as exc:
                save(f'column_{first+j:03d}_failure', dict(column=first+j, rhs=R[:, j].copy(), reason=str(exc)))
                raise
        correction = cross.left(X);effective[:, first:stop] -= correction;Rc += R@c[first:stop]
        save(f'block_{first:03d}', dict(first=first, stop=stop, R=R, X=X, correction=correction,
            S_facts=facts, logical_completed=logical, elapsed_seconds=perf_counter()-started,
            cross_seconds=dict(cross.seconds),Q_column_gate=dict(cross.right_facts),cross_retained_bytes=cross.retained_bytes(),
            live_block_array_bytes=R.nbytes+X.nbytes+correction.nbytes+effective.nbytes+original_D.nbytes))
    return effective, Rc, dict(logical=logical, blocks=(dimension+7)//8, seconds=perf_counter()-started,
                              cross_seconds=dict(cross.seconds),saved_Q_rhs=cross.saved_Q_rhs)


class SetupCheckedTraceFactor:
    """Keep only LU/pivots; original-D residual is measured at setup, not apply."""
    __slots__ = ('factor', 'dimension', 'setup_facts')

    def __init__(self, matrix, *, save):
        save('matrix', dict(D=matrix, matrix_sha256=hashlib.sha256(matrix.tobytes()).hexdigest()))
        factor, defect = checked_lu(matrix)
        if np.shares_memory(factor[0], matrix): raise ValueError('factor retains original D storage')
        self.factor, self.dimension = factor, len(matrix)
        c = np.arange(1, len(matrix)+1)+1j;rhs = matrix@c;solution = lu_solve(factor, rhs)
        error = relative_defect(matrix@solution-rhs, matrix@solution, rhs)
        self.setup_facts = dict(matrix_sha256=hashlib.sha256(matrix.tobytes()).hexdigest(),
            factor_relative=defect, witness_relative=error, setup_original_D_residual='measured',
            runtime_original_D_residual='not_measured', retained_bytes=sum(v.nbytes for v in factor))
        save('factor', dict(D=matrix, LU=factor[0], pivots=factor[1], rhs=rhs, solution=solution, facts=self.setup_facts))
        if not np.isfinite(error) or error > 1e-11: raise ValueError('setup original D witness failed')
        # Both branches use the identical factor and RHS; do not imply all-RHS accuracy.
        other = self.apply(rhs)
        same = solution.dtype == other.dtype and solution.shape == other.shape and solution.tobytes() == other.tobytes()
        save('factor_only_same_action', dict(bitwise_equal=same, fixed_rhs=rhs))
        if not same: raise ValueError('factor-only action changed')

    def apply(self, rhs):
        if rhs.shape != (self.dimension,) or not np.isfinite(rhs).all(): raise ValueError('invalid factor-only RHS')
        before = rhs.copy();value = lu_solve(self.factor, rhs)
        if not np.array_equal(rhs, before) or not np.isfinite(value).all(): raise ValueError('factor-only finite/input gate')
        return value
