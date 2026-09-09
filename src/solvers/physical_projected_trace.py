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
        started = perf_counter();self.sample();out = np.zeros((self.coarse_rows, stop-first), complex)
        per_column = np.zeros(stop-first);worst_cell = np.full(stop-first, -1, dtype=int)
        for cell, key, injection in self.local:
            h = self.classes[key];A, Q = h['A'], h['Q']
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
        self.sample();self.seconds['R'] += perf_counter()-started
        worst = int(np.argmax(per_column))
        self.right_facts = dict(worst_relative=float(per_column[worst]), column=first+worst,
            cell=int(worst_cell[worst]), per_column_relative=per_column.copy(), limit=1e-11)
        return out

    def left(self, values):
        """L times <=8 coarse columns; W supplies the already condensed P."""
        if values.ndim != 2 or values.shape[0] != self.coarse_rows or not 1 <= values.shape[1] <= 8:
            raise ValueError('L input must contain one to eight coarse columns')
        started = perf_counter();self.sample();expanded = np.column_stack([expand_primal(v, self.coarse_mapping) for v in values.T])
        out = np.zeros((self.dimension, values.shape[1]), complex)
        for cell, key, injection in self.local:
            h = self.classes[key]
            out += injection.conj().T@(h['A']@(h['W']@expanded[self.coarse_mapping['dofmap'][cell]]))
        for coupling, _, coarse in self.ports:
            amplitude = coarse['projection_values']@values[coarse['projection_rows']]/coarse['normalization_h']
            out += np.outer(coupling, amplitude)
        self.sample();self.seconds['L'] += perf_counter()-started
        return out

    def retained_bytes(self):
        return int(self.offsets.nbytes+sum(J.data.nbytes+J.indices.nbytes+J.indptr.nbytes for _, _, J in self.local)
                   +sum(left.nbytes+right.nbytes for left, right, _ in self.ports))


def projected_local_oracle(cross, original_D, solve_one, *, save, sample=lambda: None,
                           save_success_arrays=True):
    """Exactly dimension logical S solves; persist every block and any failed RHS."""
    dimension = cross.dimension
    if original_D.shape != (dimension, dimension): raise ValueError('patch D shape differs')
    effective = original_D.copy();Rc = np.zeros(cross.coarse_rows, complex)
    c = np.arange(1, dimension+1)+1j;started = perf_counter();logical = 0
    for first in range(0, dimension, 8):
        stop = min(first+8, dimension);sample();R = cross.right(first, stop);X = np.empty_like(R);facts = []
        for j in range(stop-first):
            value = None; row = None
            try:
                value, row = solve_one(R[:, j].copy());logical += 1
                if not np.isfinite(value).all() or not np.isfinite(row['relative']) or row['relative'] > 1e-10:
                    raise ValueError('S column did not pass native true residual')
                X[:, j] = value;facts.append(row)
            except BaseException as exc:
                save(f'column_{first+j:03d}_failure', dict(column=first+j, rhs=R[:, j].copy(),
                    solution=None if value is None else value.copy(), facts=row, reason=str(exc)))
                raise
        correction = cross.left(X);effective[:, first:stop] -= correction;Rc += R@c[first:stop]
        record = dict(first=first, stop=stop,
            S_facts=facts, logical_completed=logical, elapsed_seconds=perf_counter()-started,
            cross_seconds=dict(cross.seconds),Q_column_gate=dict(cross.right_facts),cross_retained_bytes=cross.retained_bytes(),
            live_block_array_bytes=R.nbytes+X.nbytes+correction.nbytes+effective.nbytes+original_D.nbytes,
            successful_arrays_persisted=save_success_arrays)
        if save_success_arrays:record.update(R=R, X=X, correction=correction)
        save(f'block_{first:03d}', record)
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

    @classmethod
    def from_saved(cls, lu, pivots, *, facts=None):
        """Restore one hash-bound LU without retaining its original matrix.

        The formal projected route reuses the already-qualified 144-by-144
        factors.  Reconstructing them with ``checked_lu`` would silently turn
        a restore into a new 252-block setup, so this constructor only checks
        the saved factor layout and finite data.
        """
        lu = np.asarray(lu)
        pivots = np.asarray(pivots)
        if lu.ndim != 2 or lu.shape[0] != lu.shape[1] or lu.dtype != np.complex128:
            raise ValueError('saved projected LU must be square complex128')
        if pivots.shape != (lu.shape[0],) or not np.issubdtype(pivots.dtype, np.integer):
            raise ValueError('saved projected pivots have the wrong shape')
        if (not np.isfinite(lu).all() or np.any(pivots < 0) or
                np.any(pivots >= lu.shape[0])):
            raise ValueError('saved projected factor is nonfinite or has invalid pivots')
        restored = object.__new__(cls)
        restored.factor = (np.array(lu, copy=True), np.array(pivots, dtype=np.int32, copy=True))
        restored.dimension = int(lu.shape[0])
        restored.setup_facts = dict(facts or {})
        restored.setup_facts.update(
            restored_factor=True,
            retained_original_D=False,
            runtime_original_D_residual='not_measured',
        )
        return restored

    def apply(self, rhs):
        if rhs.shape != (self.dimension,) or not np.isfinite(rhs).all(): raise ValueError('invalid factor-only RHS')
        before = rhs.copy();value = lu_solve(self.factor, rhs)
        if not np.array_equal(rhs, before) or not np.isfinite(value).all(): raise ValueError('factor-only finite/input gate')
        return value


def projected_residual_split(xi, indices, weights, packets, action, *, sample=lambda: None):
    """One fixed coefficient input; stream saved D/LU, without changing any PC.

    q-p denotes outside-patch coupling only if D=R T R^T was qualified elsewhere.
    Norms here are coefficient Euclidean norms, not physical field L2 norms.
    """
    xi = np.asarray(xi); indices = np.asarray(indices); weights = np.asarray(weights)
    if xi.ndim != 1 or weights.shape != xi.shape or indices.ndim != 2:
        raise ValueError('invalid coefficient/map shape')
    if not np.issubdtype(indices.dtype, np.integer) or np.any(indices < 0) or np.any(indices >= len(xi)):
        raise ValueError('invalid patch indices')
    if any(len(np.unique(rows)) != len(rows) for rows in indices):
        raise ValueError('duplicate row within patch')
    pou = np.zeros(len(xi)); np.add.at(pou, indices.ravel(), weights[indices].ravel()**2)
    if not np.isfinite(xi).all() or not np.isfinite(weights).all() or not np.allclose(pou, 1., rtol=0., atol=1e-14):
        raise ValueError('nonfinite input or squared PoU does not sum to one')
    z = np.zeros_like(xi); l = np.zeros_like(xi); p = np.zeros_like(xi)
    local_scale = float(np.linalg.norm(xi)); local_max = 0.; solved = 0
    for rows, packet in zip(indices, packets, strict=True):
        sample(); D, factor = packet
        if D.shape != (len(rows), len(rows)):
            raise ValueError('local matrix shape differs')
        w = weights[rows]; rhs = w*xi[rows]; value = lu_solve(factor, rhs)
        image = D@value
        error = relative_defect(image-rhs, image, rhs)
        if not np.isfinite(error) or error > 1e-11:
            raise ValueError('saved local solve operation-scale gate')
        np.add.at(z, rows, w*value); np.add.at(l, rows, w*image)
        np.add.at(p, rows, D@(w*value))
        local_scale += float(np.linalg.norm(w*image)); local_max = max(local_max, error); solved += 1
        del packet, D, factor, value, image
    q = np.asarray(action(z))
    if q.shape != xi.shape or not all(np.isfinite(v).all() for v in (z, l, p, q)):
        raise ValueError('invalid exact coefficient action')
    terms = np.stack((q-p, p-l, l-xi)); total = q-xi
    scale = float(sum(np.linalg.norm(v) for v in (q, p, l, xi)))
    closure = float(np.linalg.norm(terms.sum(axis=0)-total)/max(scale, np.finfo(float).tiny))
    local = float(np.linalg.norm(l-xi)/max(local_scale, np.finfo(float).tiny))
    if max(closure, local) > 1e-11:
        raise ValueError('split or local PoU operation-scale gate')
    norm = float(np.linalg.norm(xi)); gram = terms.conj()@terms.T
    return dict(xi=xi.copy(), z=z, l=l, p=p, q=q, terms=terms, total=total, gram=gram,
        gram_normalized=gram/norm**2 if norm else None,
        relative_norms=np.linalg.norm(terms, axis=1)/norm if norm else None,
        total_relative=float(np.linalg.norm(total)/norm) if norm else None,
        xi_norm=norm, identity_relative=closure, local_relative=local,
        identity_operation_scale=scale, local_operation_scale=local_scale,
        local_solve_max_relative=local_max, local_solves=solved, pou_max_defect=float(np.max(np.abs(pou-1))))


class ProjectedTraceFactorStore:
    """One independent factor per patch; fixed PoU weights on both sides."""
    def __init__(self, indices, weights, offsets):
        self.indices=np.array(indices,dtype=np.int64,copy=True)
        self.weights=np.array(weights,dtype=float,copy=True)
        self.offsets=np.array(offsets,dtype=np.int64,copy=True)
        if self.indices.ndim!=2 or self.offsets[0]!=0 or self.offsets[-1]!=len(self.weights):
            raise ValueError('invalid projected patch maps')
        if np.any(self.indices<0) or np.any(self.indices>=len(self.weights)):
            raise ValueError('projected patch index outside coefficient space')
        multiplicity=np.bincount(self.indices.ravel(),minlength=len(self.weights))
        if np.any(multiplicity==0) or not np.array_equal(self.weights,1./np.sqrt(multiplicity)):
            raise ValueError('fixed PoU weights differ')
        if np.any(np.diff(self.offsets)<=0):raise ValueError('invalid coefficient offsets')
        self.factors=[];self.counts=dict(applications=0,patch_apply_rhs=0,patch_LU=0)

    def append(self, matrix, *, save):
        if len(self.factors)>=len(self.indices) or matrix.shape!=(self.indices.shape[1],)*2:
            raise ValueError('projected factor store capacity/shape')
        factor=SetupCheckedTraceFactor(matrix,save=save)
        self.factors.append(factor);self.counts['patch_LU']+=1
        return factor.setup_facts

    def append_saved_factor(self, lu, pivots, *, facts=None):
        """Append one existing factor without refactoring or retaining ``D``."""
        if len(self.factors) >= len(self.indices):
            raise ValueError('projected factor store capacity')
        factor = SetupCheckedTraceFactor.from_saved(lu, pivots, facts=facts)
        if factor.dimension != self.indices.shape[1]:
            raise ValueError('saved projected factor dimension differs')
        self.factors.append(factor)
        self.counts['restored_factors'] = self.counts.get('restored_factors', 0) + 1
        return factor.setup_facts

    def apply(self, coefficients, sample):
        if len(self.factors)!=len(self.indices):raise ValueError('incomplete projected store')
        rhs=np.concatenate(coefficients)
        if rhs.shape!=self.weights.shape or not np.isfinite(rhs).all():raise ValueError('invalid trace coefficients')
        result=np.zeros_like(rhs)
        for i,(rows,factor) in enumerate(zip(self.indices,self.factors,strict=True)):
            if i%8==0:sample()
            local=self.weights[rows]*rhs[rows];value=factor.apply(local)
            np.add.at(result,rows,self.weights[rows]*value)
        sample()
        if not np.isfinite(result).all():raise ValueError('nonfinite projected trace result')
        self.counts['applications']+=1;self.counts['patch_apply_rhs']+=len(self.factors)
        self.last_facts=dict(logical_rhs=len(self.factors),runtime_original_D_residual='not_measured',
            finite=True,setup_only_original_D_checks=True)
        return [result[a:b] for a,b in zip(self.offsets[:-1],self.offsets[1:],strict=True)]

    def storage(self):
        return [self.indices,self.weights,self.offsets,[f.factor for f in self.factors]]


def structured_cell_parity_groups(cell_coordinates):
    """Return the fixed structured ``(i+j+k) % 2`` factor groups.

    Coordinates are supplied by the tensor-product mesh order, not inferred
    from rows, materials, residuals, or a reference field.  The returned
    arrays always enumerate group 0 completely before group 1; the groups are
    an ordered additive split and are not asserted to be uncoupled.
    """
    coordinates = np.asarray(cell_coordinates)
    if coordinates.ndim != 2 or coordinates.shape[1] != 3 or not coordinates.shape[0]:
        raise ValueError('structured cell coordinates must have shape (n, 3)')
    if np.issubdtype(coordinates.dtype, np.integer):
        integer = coordinates.astype(np.int64, copy=False)
    else:
        if not np.isfinite(coordinates).all() or not np.allclose(
                coordinates, np.rint(coordinates), rtol=0., atol=0.):
            raise ValueError('structured cell coordinates must be exact integers')
        integer = np.rint(coordinates).astype(np.int64)
    parity = np.mod(integer.sum(axis=1), 2)
    groups = (np.flatnonzero(parity == 0), np.flatnonzero(parity == 1))
    if any(len(group) == 0 for group in groups):
        raise ValueError('structured parity split must contain both groups')
    return groups


def structured_mesh_cell_coordinates(mesh, axis_values):
    """Recover canonical cell coordinates from the actual mesh geometry.

    The coordinate is assigned by the cell centroid and the explicit Stage-4
    axis planes.  This keeps the factor-cell correspondence tied to the
    current physical mesh rather than assuming a row or construction order.
    """
    axes = tuple(np.asarray(axis, dtype=float) for axis in axis_values)
    if len(axes) != 3 or any(axis.ndim != 1 or len(axis) < 2 or
                              not np.isfinite(axis).all() or
                              np.any(np.diff(axis) <= 0) for axis in axes):
        raise ValueError('structured mesh axes are invalid')
    geometry = np.asarray(mesh.geometry.x, dtype=float)
    dofmap = np.asarray(mesh.geometry.dofmap, dtype=np.int64)
    if dofmap.ndim != 2 or dofmap.shape[0] != mesh.topology.index_map(mesh.topology.dim).size_local:
        raise ValueError('structured mesh cell geometry map is incomplete')
    centers = geometry[dofmap].mean(axis=1)
    coordinates = np.empty((len(centers), 3), dtype=np.int64)
    for cell, center in enumerate(centers):
        for direction, axis in enumerate(axes):
            index = int(np.searchsorted(axis, center[direction], side='right') - 1)
            if index < 0 or index >= len(axis) - 1:
                raise ValueError('cell centroid falls outside structured axes')
            expected = .5 * (axis[index] + axis[index + 1])
            if not np.isclose(center[direction], expected, rtol=0., atol=1e-11):
                raise ValueError('cell centroid is not a canonical structured cell')
            coordinates[cell, direction] = index
    expected_count = int(np.prod([len(axis) - 1 for axis in axes]))
    if len(coordinates) != expected_count or len(np.unique(coordinates, axis=0)) != expected_count:
        raise ValueError('structured mesh cells do not form the complete canonical grid')
    return coordinates


class ProjectedSequentialTraceFactorStore(ProjectedTraceFactorStore):
    """Two-group sequential projected inverse with one complete ``T`` call.

    With ``M0`` and ``M1`` the two additive patch groups, the apply is
    ``d0=M0*f``, ``f1=f-T*d0``, ``d1=M1*f1``, and ``z=d0+d1``.  Thus the
    realized operator is ``M0 + M1 - M1*T*M0``; the groups are an ordered
    sequential schedule, not an assertion that the physical blocks decouple.
    """
    def __init__(self, indices, weights, offsets, cell_coordinates, complete_T,
                 *, sample=lambda: None):
        super().__init__(indices, weights, offsets)
        self.group_members = structured_cell_parity_groups(cell_coordinates)
        if len(self.group_members[0]) + len(self.group_members[1]) != len(self.indices):
            raise ValueError('cell coordinate/factor count differs')
        self.set_complete_T(complete_T)
        self.sample = sample
        self.counts.update(
            sequential_applications=0,
            group0_patch_apply_rhs=0,
            group1_patch_apply_rhs=0,
            patch_MatSolve=0,
            T_started=0,
            T_completed=0,
            additive_applications=0,
        )

    def set_complete_T(self, complete_T):
        if not callable(complete_T):
            raise TypeError('complete projected T must be callable')
        self.complete_T = complete_T

    def _apply_group(self, rhs, group, label):
        result = np.zeros_like(rhs)
        for ordinal, index in enumerate(group):
            if ordinal % 8 == 0:
                self.sample()
            rows = self.indices[index]
            value = self.factors[index].apply(self.weights[rows] * rhs[rows])
            np.add.at(result, rows, self.weights[rows] * value)
            self.counts[f'{label}_patch_apply_rhs'] += 1
            self.counts['patch_apply_rhs'] += 1
            self.counts['patch_MatSolve'] += 1
        return result

    def _flat_rhs(self, coefficients):
        if len(self.factors) != len(self.indices):
            raise ValueError('incomplete sequential projected store')
        rhs = np.concatenate(coefficients) if not isinstance(coefficients, np.ndarray) else np.asarray(coefficients)
        if rhs.shape != self.weights.shape or not np.isfinite(rhs).all():
            raise ValueError('invalid sequential projected RHS')
        return rhs

    def apply_additive(self, coefficients):
        """Apply the old all-block additive action for the finite comparison."""
        rhs = self._flat_rhs(coefficients)
        result = self._apply_group(rhs, self.group_members[0], 'group0')
        result += self._apply_group(rhs, self.group_members[1], 'group1')
        self.sample()
        self.counts['additive_applications'] += 1
        return [result[a:b] for a, b in zip(self.offsets[:-1], self.offsets[1:], strict=True)]

    def apply_explicit_sequential(self, coefficients, sample=None):
        """Return an independently staged ``d0/T/d1`` sequential apply.

        This is the finite same-input witness for the compact ``apply`` path:
        it exposes the two group solves and the complete current ``T`` as
        separate stages, while using the same saved factors and callback.
        The method is deliberately separate from ``apply`` so a comparison
        cannot pass merely because both sides call the same formula wrapper.
        """
        if sample is not None:
            previous = self.sample
            self.sample = sample
        else:
            previous = None
        try:
            rhs = self._flat_rhs(coefficients)
            d0 = self._apply_group(rhs, self.group_members[0], 'group0')
            self.counts['T_started'] += 1
            self.sample()
            T_d0 = np.asarray(self.complete_T(d0.copy()))
            self.counts['T_completed'] += 1
            if T_d0.shape != rhs.shape or not np.isfinite(T_d0).all():
                raise ValueError('explicit projected T returned an invalid vector')
            f1 = rhs - T_d0
            d1 = self._apply_group(f1, self.group_members[1], 'group1')
            result = d0 + d1
            if not np.isfinite(result).all():
                raise ValueError('explicit sequential projected result is nonfinite')
            self.counts['explicit_applications'] = self.counts.get(
                'explicit_applications', 0) + 1
            self.last_explicit_facts = dict(
                group0_factors=int(len(self.group_members[0])),
                group1_factors=int(len(self.group_members[1])),
                local_backsolves=int(len(self.indices)),
                T_calls=1,
                formula='d0=M0*f; f1=f-T*d0; d1=M1*f1; z=d0+d1',
                finite=True,
            )
            return dict(
                coefficients=[result[a:b] for a, b in zip(
                    self.offsets[:-1], self.offsets[1:], strict=True)],
                d0=d0, T_d0=T_d0, f1=f1, d1=d1, result=result,
                facts=dict(self.last_explicit_facts),
            )
        finally:
            if previous is not None:
                self.sample = previous

    def apply(self, coefficients, sample=None):
        if sample is not None:
            previous = self.sample
            self.sample = sample
        else:
            previous = None
        try:
            rhs = self._flat_rhs(coefficients)
            d0 = self._apply_group(rhs, self.group_members[0], 'group0')
            self.counts['T_started'] += 1
            self.sample()
            image = np.asarray(self.complete_T(d0.copy()))
            self.counts['T_completed'] += 1
            if image.shape != rhs.shape or not np.isfinite(image).all():
                raise ValueError('complete projected T returned an invalid vector')
            f1 = rhs - image
            d1 = self._apply_group(f1, self.group_members[1], 'group1')
            result = d0 + d1
            self.sample()
            if not np.isfinite(result).all():
                raise ValueError('nonfinite sequential projected result')
            self.counts['applications'] += 1
            self.counts['sequential_applications'] += 1
            self.last_facts = dict(
                group0_factors=int(len(self.group_members[0])),
                group1_factors=int(len(self.group_members[1])),
                local_backsolves=int(len(self.indices)),
                T_calls=1,
                T_patch_matvec=int(getattr(self.complete_T, 'counts', {}).get('patch_matvec', 0)),
                formula='M0 + M1 - M1*T*M0',
                finite=True,
            )
            return [result[a:b] for a, b in zip(self.offsets[:-1], self.offsets[1:], strict=True)]
        finally:
            if previous is not None:
                self.sample = previous

    def storage(self):
        callback_storage = []
        if self.complete_T is not None and hasattr(self.complete_T, 'storage'):
            callback_storage = self.complete_T.storage()
        return super().storage() + [callback_storage]

    def destroy(self):
        self.factors.clear()
        self.complete_T = None
        self.group_members = (np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64))
        self.indices = np.empty((0, 0), dtype=np.int64)
        self.weights = np.empty(0, dtype=float)
        self.offsets = np.empty(0, dtype=np.int64)
        self.counts.clear()
