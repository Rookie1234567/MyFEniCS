"""Audit-only streamed two-cell augmented branch matrices; no q factor API."""
from __future__ import annotations

import numpy as np
from scipy import sparse

from .y_orbit_sparse_reference import integer_admission, csr_audit, _gate


class TwoCellBranchCoordinates:
    def __init__(self, trace, condensed, context, *, global_original_H, allocation_gate, index_dtype, direct_profile=None):
        self.trace,self.context,self.index_dtype=trace,context,np.dtype(index_dtype)
        self.gate=allocation_gate
        self.width=int(trace['trace_width']);self.trace_rows=int(condensed.system.active_rows)
        self.ports=len(condensed.action_bundle['modes']);self.rows=self.trace_rows+self.ports
        if direct_profile is None:
            width_expected, trace_expected, sector_expected, replication_count = 1808, 3616, (228, 304), 2
        else:
            from .y_orbit_direct_profile import direct_profile_metadata
            profile = direct_profile_metadata(direct_profile)
            width_expected, trace_expected = profile.trace_rows_per_q, profile.local_trace_rows
            sector_expected, replication_count = profile.sector_port_counts, profile.replication_count
            if context.direct_profile_name != profile.name:
                raise ValueError('direct branch coordinates/context profile differs')
        if trace['ny']!=2 or self.width!=width_expected or self.trace_rows!=trace_expected or self.ports!=sector_expected[context.twist_index]:
            raise ValueError('fixed complete two40 p4 trace/port inventory required')
        carrier=condensed.action_bundle['dtn_action'].carrier
        h=np.asarray([e.normalization_h for e in carrier.entries])
        global_h=np.asarray(global_original_H)[np.asarray(context.original_mode_indices)]
        if (h.shape!=global_h.shape or np.any(h<=0) or not np.isfinite(h).all()
                or np.max(np.abs(h-global_h/replication_count)/h)>1e-12):
            raise ValueError('actual local originalH must equal frozen globalH/K per mode')
        self.scale=1/np.sqrt(h)
        branch=np.asarray(context.local_branch_indices)
        self.aliases=tuple(np.flatnonzero(branch==b) for b in (0,1))
        expected=((76,152) if context.twist_index==0 else (152,152)) if direct_profile is None else tuple(profile.q_port_counts[q] for q in context.global_q_indices)
        if tuple(map(len,self.aliases))!=expected or not np.array_equal(np.sort(np.concatenate(self.aliases)),np.arange(self.ports)):
            raise ValueError('both branches must cover every local physical alias exactly once')
        _gate(allocation_gate,'local_trace_R_F_product',payload=4*sum(a.nbytes for m in (trace['R_t'],trace['F_t'])
              for a in (m.data,m.indices,m.indptr)),workspace=16*1024**2)
        self.qt=(trace['R_t']@trace['F_t']).tocsr()
        hcell=float(np.diff(context.local_axes[1])[0])
        eta=np.asarray([np.exp(1j*complex(m.gamma)*hcell) for m in condensed.action_bundle['modes']])
        expected_eta=np.asarray([context.eta*(-1)**int(b) for b in branch])
        if max(np.max(np.abs(eta-expected_eta)),np.max(np.abs(eta**2-context.tau)))>1e-12:
            raise ValueError('physical Gamma_n aliases disagree with explicit eta/tau branches')
        self.audit={'global_q_indices':list(context.global_q_indices),'alias_counts':list(expected),
                    'original_H_scale_verified':True,'port_eta':[ [v.real,v.imag] for v in eta],
                    'positive_H_coordinates':True,'global_matrices_created':False,'numeric_factor_calls':0,
                    **({} if direct_profile is None else {'direct_profile': profile.name, 'H_global_to_local_ratio': replication_count})}

    def q_map(self, branch):
        if branch not in (0,1):raise ValueError('both local branches have explicit indices0/1')
        ids=self.aliases[branch]
        payload=sum(a.nbytes for a in (self.qt.data,self.qt.indices,self.qt.indptr))
        _gate(self.gate,'local_branch_q_map_slicing_and_ports',payload=3*payload+len(ids)*64,
              workspace=2*payload,all_local_polynomial_channels=True)
        ports=sparse.csr_matrix((self.scale[ids].astype(complex),(ids,np.arange(len(ids)))),shape=(self.ports,len(ids)))
        return sparse.block_diag((self.qt[:,branch*self.width:(branch+1)*self.width],ports),format='csr')


class TwoCellBlockProvider:
    """Project borrowed exact cell/port contributions, one block at a time.

    Native reduced S is never materialized. There is no SuperLU constructor,
    factor callback, whole-Ny reference matrix or Fourier matrix here.
    """
    def __init__(self, condensed, coordinates, *, allocation_gate,
                 compact_projection_max_owned_bytes=None, compact_projection_tile_width=32):
        self.condensed,self.coordinates,self.gate=condensed,coordinates,allocation_gate
        # Explicit research opt-in; None preserves the legacy projection path.
        if compact_projection_max_owned_bytes is not None:
            from .bounded_compact_q_projection import _positive_integer
            _positive_integer(compact_projection_max_owned_bytes, 'compact_projection_max_owned_bytes')
            _positive_integer(compact_projection_tile_width, 'compact_projection_tile_width')
            if not getattr(getattr(condensed, 'action', None), 'uses_port_block_representation', False):
                raise ValueError('bounded q projection requires explicit compact port layout')
        self.compact_projection_max_owned_bytes = compact_projection_max_owned_bytes
        self.compact_projection_tile_width = compact_projection_tile_width
        self.calls=0

    def block(self,p,q):
        if getattr(getattr(self.condensed, 'action', None), 'uses_port_block_representation', False):
            return self._block_compact(p, q)
        c=self.coordinates;left=c.q_map(p);right=c.q_map(q)
        shape=(left.shape[1],right.shape[1]);integer_admission(shape,0,index_dtype=c.index_dtype)
        result=sparse.csr_matrix(shape,dtype=complex)
        for rows,cols,values,label in self.condensed.iter_contributions(allocation_gate=self.gate):
            rows,cols=np.asarray(rows),np.asarray(cols);values=np.asarray(values)
            if (rows.dtype.kind not in 'iu' or cols.dtype.kind not in 'iu' or rows.ndim!=1 or cols.ndim!=1
                    or values.shape!=(len(rows),len(cols)) or values.dtype.hasobject or not np.isfinite(values).all()
                    or (len(rows) and (rows.min()<0 or rows.max()>=c.rows))
                    or (len(cols) and (cols.min()<0 or cols.max()>=c.rows))):
                raise ValueError('invalid original reduced contribution: '+str(label))
            before=sum(a.nbytes for m in (left,right) for a in (m.data,m.indices,m.indptr))
            _gate(self.gate,'local_contribution_q_slice_'+str(label),payload=2*before,
                  workspace=before+len(rows)*8+len(cols)*8)
            lr,rr=left[rows,:].tocsr(),right[cols,:].tocsr()
            support_p,support_q=np.unique(lr.indices),np.unique(rr.indices)
            if not len(support_p) or not len(support_q):continue
            count=len(support_p)*len(support_q)
            integer_admission(shape,int(result.nnz)+count,index_dtype=c.index_dtype)
            dense_count=len(rows)*len(support_p)+len(cols)*len(support_q)+len(support_p)*len(cols)+count
            _gate(self.gate,'streamed_local_congruence_'+str(label),payload=dense_count*16,
                  workspace=count*(16+2*c.index_dtype.itemsize)+2*int(result.data.nbytes+result.indices.nbytes+result.indptr.nbytes))
            l=lr[:,support_p].toarray();r=rr[:,support_q].toarray()
            projected=l.conj().T@values@r
            ii,jj=np.nonzero(projected)  # exact zeros only; no magnitude threshold
            term=sparse.coo_matrix((projected[ii,jj],(support_p[ii],support_q[jj])),shape=shape).tocsr()
            result=(result+term).tocsr()
            del lr,rr,l,r,projected,term
        self.calls+=1
        csr_audit(result,petsc_index_dtype=c.index_dtype)
        return result

    def _block_compact(self, p, q):
        """Project the exact cached layout without creating an Hhat square.

        This is a narrow consumer of P6CellCondensedAction's typed recipes.
        Current named owners are disclosed separately from additional bytes;
        the caller's fresh RSS gate covers earlier q outputs and all other
        retained objects. CSR/CSC bounds use the actual ABI and native index
        widths before allocation. Sparse/BLAS native workspace remains an
        explicit allowance, never an RSS measurement or fill prediction.
        """
        from .original_port_blocks import (
            CachedPortCorrection, DenseOriginalPortBlock, DiagonalOriginalPortBlock,
        )

        c = self.coordinates
        action = self.condensed.action
        if (action._destroyed or action.condensed._destroyed
                or action.port_coupling_mode != 'cached'
                or action.condensed.comm.Get_size() != 1):
            raise ValueError('compact provider requires a live MPI1 cached action')
        if action._H_p is not None or action._Hhat is not None:
            raise ValueError('compact provider owner unexpectedly retains H/Hhat arrays')
        nt = int(action.condensed.active_rows)
        np_ = int(action.condensed.appended_rows)
        if c.rows != nt + np_:
            raise ValueError('compact native trace/port inventory differs from coordinates')
        integer_admission((c.rows, c.rows), 0, index_dtype=c.index_dtype)
        # Admit Python owner/label inventories before constructing them.
        _gate(self.gate, 'compact_provider_owner_inventory', workspace=512 * (
            1 + len(action._cells) + np_), no_new_unprojected_port_square_created=True)
        expected = {'ports/H_original': ('H', None)}
        for index, cell in enumerate(action._cells):
            expected[f'volume/cell/{index}'] = ('volume', cell)
            if len(cell.ports):
                expected[f'cell/C_hat/{index}'] = ('C', cell)
                expected[f'cell/-D_hat/{index}'] = ('D', cell)
                expected[f'cell/Hhat_correction/{index}'] = ('correction', cell)
        for port in action._direct_B_active:
            expected[f'direct/C/port/{port}'] = ('direct_C', port)
        for port in action._direct_D_active:
            expected[f'direct/-D/port/{port}'] = ('direct_D', port)
        seen = set()
        carrier = self.condensed.action_bundle['dtn_action'].carrier
        keys = tuple(tuple(entry.mode_key) for entry in carrier.entries)
        if action._original_port_block.mode_keys != keys or len(keys) != np_:
            raise ValueError('compact original H keys differ from complete carrier order')

        # Count unique backing owners of all named cell/cache/port arrays.
        # Views, shared local classes and cached correction aliases count once.
        borrowed = {}
        def retain(array):
            if array is None:
                return
            owner = array
            while isinstance(getattr(owner, 'base', None), np.ndarray):
                owner = owner.base
            borrowed[id(owner)] = int(owner.nbytes)
        for cell in action._cells:
            for field in ('original_interiors', 'original_trace', 'active_ids',
                          'S_V', 'recovery', 'trace_from_interior', 'Bi', 'Bt',
                          'Di', 'Dt', 'ports', 'Bhat', 'Dhat', 'XiB', 'Hlocal'):
                retain(getattr(cell, field))
            for array in (*cell.interior_lu, cell.expansion.data,
                          cell.expansion.indices, cell.expansion.indptr):
                retain(array)
        for term in action._port_terms.values():
            for field in ('Bi', 'Di', 'Bt', 'Dt', 'H', 'port_indices'):
                retain(getattr(term, field))
        for mapping in (action._direct_B_original, action._direct_D_original,
                        action._direct_B_active, action._direct_D_active):
            for pair in mapping.values():
                for array in pair:
                    retain(array)
        for array in action._original_port_block.numeric_arrays:
            retain(array)
        borrowed_bytes = sum(borrowed.values())
        del borrowed

        def sparse_bytes(matrix):
            return int(matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes)

        left, right = c.q_map(p), c.q_map(q)
        for matrix in (left, right):
            if self.compact_projection_max_owned_bytes is None:
                csr_audit(matrix, petsc_index_dtype=c.index_dtype)
            else:
                from .bounded_compact_q_projection import audit_csr_scalar
                audit_csr_scalar(matrix, index_dtype=c.index_dtype)
            if matrix.shape[0] != c.rows:
                raise ValueError('compact q map has the wrong native row inventory')
        shape = (left.shape[1], right.shape[1])
        integer_admission(shape, 0, index_dtype=c.index_dtype)
        ibytes = max(c.index_dtype.itemsize, np.dtype(np.intp).itemsize,
                     left.indices.dtype.itemsize, left.indptr.dtype.itemsize,
                     right.indices.dtype.itemsize, right.indptr.dtype.itemsize)
        maps_bytes = sparse_bytes(left) + sparse_bytes(right)
        def gate(label, payload=0, workspace=0, **facts):
            _gate(self.gate, 'compact_provider/' + label, payload=payload,
                  workspace=workspace, borrowed_action_backing_bytes=borrowed_bytes,
                  current_q_map_bytes=maps_bytes,
                  current_q_result_bytes=facts.pop('bounded_current_result_bytes',
                      0 if result is None else sparse_bytes(result)),
                  current_objects_in_fresh_RSS=True,
                  earlier_q_outputs_in_fresh_RSS=True,
                  native_index_itemsize_upper=ibytes,
                  PETSc_index_itemsize_bytes=c.index_dtype.itemsize,
                  CSR_and_CSC_workspaces_included=True,
                  numeric_factor_count=0, no_new_unprojected_port_square_created=True,
                  native_sparse_and_BLAS_workspace_unknown=True, **facts)
        result = None
        bounded = None
        if self.compact_projection_max_owned_bytes is None:
            gate('empty_q_result', payload=(shape[0] + 1) * ibytes)
            result = sparse.csr_matrix(shape, dtype=np.complex128)
        else:
            from .bounded_compact_q_projection import BoundedCompactQAccumulator
            bounded = BoundedCompactQAccumulator(
                shape, max_owned_bytes=self.compact_projection_max_owned_bytes,
                tile_width=self.compact_projection_tile_width,
                index_dtype=c.index_dtype, gate=gate)

        def equal_ids(ids, expected_ids):
            if bounded is not None:
                return ids.shape == expected_ids.shape and all(
                    int(a) == int(b) for a, b in zip(ids, expected_ids, strict=True))
            return np.array_equal(ids, expected_ids)
        def port_ids(ids, ports):
            return len(ids) == len(ports) and all(
                int(value) == nt + int(port) for value, port in zip(ids, ports, strict=True))
        def readonly_finite(array, *, complex_values=False):
            if not isinstance(array, np.ndarray) or array.flags.writeable:
                raise ValueError('compact payload must borrow readonly NumPy arrays')
            if complex_values and array.dtype != np.dtype(np.complex128):
                raise ValueError('compact numeric payload must be complex128')
            if bounded is not None:
                if any(not np.isfinite(value) for value in array.flat):
                    raise ValueError('compact contribution contains nonfinite values')
            else:
                # Legacy row-wise masks never allocate a factor/matrix square.
                for row in array:
                    if not np.isfinite(row).all():
                        raise ValueError('compact contribution contains nonfinite values')

        for rows, cols, values, label in self.condensed.iter_contributions(allocation_gate=self.gate):
            if label not in expected or label in seen:
                raise ValueError('compact contribution label is unknown or duplicated: ' + str(label))
            seen.add(label)
            kind, owner = expected[label]
            for ids in (rows, cols):
                if (not isinstance(ids, np.ndarray) or ids.ndim != 1 or ids.dtype.kind not in 'iu'
                        or ids.flags.writeable
                        or any(int(v) < 0 or int(v) >= c.rows for v in ids)
                        or len(set(map(int, ids))) != len(ids)):
                    raise ValueError('invalid compact native contribution indices: ' + label)
            if kind == 'H':
                if (values is not action._original_port_block
                        or not isinstance(values, (DiagonalOriginalPortBlock, DenseOriginalPortBlock))
                        or values.count != np_ or values.mode_keys != keys
                        or not all(int(v) == nt + i for i, v in enumerate(rows))
                        or not equal_ids(rows, cols) or len(rows) != np_):
                    raise ValueError('compact original H recipe or key/index order differs')
                arrays = values.numeric_arrays
                expected_h_shape = (np_,) if isinstance(values, DiagonalOriginalPortBlock) else (np_, np_)
                if len(arrays) != 1 or arrays[0].shape != expected_h_shape:
                    raise ValueError('compact original H stored shape differs from its representation')
                for array in arrays:
                    readonly_finite(array, complex_values=True)
                del arrays
            elif kind == 'correction':
                if (not isinstance(values, CachedPortCorrection)
                        or values.port_indices is not owner.ports
                        or values.Di is not owner.Di or values.XiB is not owner.XiB
                        or not port_ids(rows, owner.ports) or not equal_ids(rows, cols)):
                    raise ValueError('compact correction differs from exact borrowed cell recipe')
                for array in (values.port_indices, values.Di, values.XiB):
                    readonly_finite(array, complex_values=array is not values.port_indices)
                if (values.Di.ndim != 2 or values.XiB.ndim != 2
                        or values.Di.shape != (len(rows), values.XiB.shape[0])
                        or values.XiB.shape[1] != len(cols)):
                    raise ValueError('compact correction factors have incompatible dimensions')
            else:
                readonly_finite(values, complex_values=True)
                if values.shape != (len(rows), len(cols)):
                    raise ValueError('compact dense contribution dimensions differ')
                if kind == 'volume':
                    valid = equal_ids(rows, owner.active_ids) and equal_ids(cols, owner.active_ids)
                elif kind == 'C':
                    valid = equal_ids(rows, owner.active_ids) and port_ids(cols, owner.ports)
                elif kind == 'D':
                    valid = port_ids(rows, owner.ports) and equal_ids(cols, owner.active_ids)
                elif kind == 'direct_C':
                    valid = equal_ids(rows, action._direct_B_active[owner][0]) and port_ids(cols, (owner,))
                else:
                    valid = port_ids(rows, (owner,)) and equal_ids(cols, action._direct_D_active[owner][0])
                if not valid:
                    raise ValueError('compact contribution native row/column order differs: ' + label)

            if bounded is not None:
                bounded.add(left, right, rows, cols, values, label)
                del rows, cols, values
                continue

            # Upper bounds for row gathers, support discovery and sparse
            # column slicing include actual CSR/CSC index widths.
            row_slice_bytes = 2 * maps_bytes + (len(rows) + len(cols) + 2) * ibytes
            gate('q_slices/' + label, payload=row_slice_bytes,
                 workspace=maps_bytes + (left.nnz + right.nnz) * ibytes)
            lr, rr = left[rows, :].tocsr(), right[cols, :].tocsr()
            support_p, support_q = np.unique(lr.indices), np.unique(rr.indices)
            if not len(support_p) or not len(support_q):
                del lr, rr, support_p, support_q, rows, cols, values
                continue
            count = int(len(support_p)) * int(len(support_q))
            upper = int(result.nnz) + count
            integer_admission(shape, upper, index_dtype=c.index_dtype)
            integer_admission(shape, upper, index_dtype=np.intp)
            sparse_upper = upper * (16 + ibytes) + (shape[0] + 1) * ibytes
            term_upper = count * (16 + 2 * ibytes) + (shape[0] + 1) * ibytes
            slice_bytes = sparse_bytes(lr) + sparse_bytes(rr)
            if isinstance(values, DiagonalOriginalPortBlock):
                # Sparse row scaling implements diagonal H without even a
                # temporary sector square or dense q-support rectangle.
                gate('diagonal_H_projection/' + label,
                     payload=2 * slice_bytes + term_upper + sparse_upper,
                     workspace=2 * term_upper + sparse_upper + slice_bytes,
                     current_contribution_slice_bytes=slice_bytes)
                weighted = rr.copy()
                for index, diagonal in enumerate(values.diagonal):
                    first, last = int(weighted.indptr[index]), int(weighted.indptr[index + 1])
                    weighted.data[first:last] *= diagonal
                dual = lr.conjugate().T  # CSC view of a bounded conjugated CSR
                term = (dual @ weighted).tocsr()
                del weighted, dual
            else:
                lp, rq = len(support_p), len(support_q)
                if isinstance(values, CachedPortCorrection):
                    ni = int(values.XiB.shape[0])
                    factor_entries = lp * ni + ni * rq
                else:
                    factor_entries = lp * len(cols)
                dense_entries = 2 * len(rows) * lp + len(cols) * rq + factor_entries + count
                gate('factored_or_dense_projection/' + label,
                     payload=16 * dense_entries + 2 * slice_bytes + term_upper + sparse_upper,
                     workspace=16 * (factor_entries + count) + 2 * term_upper + sparse_upper,
                     borrowed_correction_factors=isinstance(values, CachedPortCorrection),
                     current_contribution_slice_bytes=slice_bytes)
                l = lr[:, support_p].toarray()
                r = rr[:, support_q].toarray()
                if isinstance(values, CachedPortCorrection):
                    dual_di = l.conj().T @ values.Di
                    xib_primal = values.XiB @ r
                    projected = dual_di @ xib_primal
                    del dual_di, xib_primal
                else:
                    matrix = values.numeric_arrays[0] if isinstance(values, DenseOriginalPortBlock) else values
                    projected = l.conj().T @ matrix @ r
                    del matrix
                if not np.isfinite(projected).all():
                    raise FloatingPointError('compact projected contribution is nonfinite: ' + label)
                ii, jj = np.nonzero(projected)  # every numerical nonzero, no cutoff
                term = sparse.coo_matrix((projected[ii, jj],
                    (support_p[ii], support_q[jj])), shape=shape).tocsr()
                del l, r, projected, ii, jj
            csr_audit(term, petsc_index_dtype=c.index_dtype)
            result = (result + term).tocsr()
            del lr, rr, support_p, support_q, term, rows, cols, values
        if seen != set(expected):
            raise ValueError('compact contribution inventory is incomplete: ' + ','.join(sorted(set(expected) - seen)))
        self.calls += 1
        if bounded is not None:
            return bounded.finish()
        csr_audit(result, petsc_index_dtype=c.index_dtype)
        return result


def audit_two_cell_blocks(provider, authority_load, *, save_csr, event):
    """Both branches/complete block columns, zero factors, unchanged1e-11 gate."""
    norms={};pairs=[];diagonal=[]
    for q in (0,1):
        for p in (0,1):
            matrix=provider.block(p,q);norm=float(sparse.linalg.norm(matrix))
            global_q=provider.coordinates.context.global_q_indices[q]
            item={'p':p,'q':q,'global_q':global_q,'shape':list(matrix.shape),'nnz':int(matrix.nnz),
                  'frobenius_norm':norm,'numeric_factor_count':0}
            if p==q:
                reference=authority_load(global_q)
                if reference.shape!=matrix.shape:raise ValueError('frozen full p4 branch dimensions differ')
                difference=matrix-reference
                item.update(authority_relative_difference=float(sparse.linalg.norm(difference)/max(sparse.linalg.norm(reference),np.finfo(float).tiny)),
                            absolute_max_difference=float(np.max(np.abs(difference.data))) if difference.nnz else 0.0)
                save_csr('global_q_'+str(global_q),matrix)
                norms[q]=norm;diagonal.append(item)
            pairs.append(item);event('quotient_block_audited_before_factor',item)
            del matrix
    for item in pairs:
        p,q=item['p'],item['q']
        if min(norms[p],norms[q])==0:raise ValueError('zero branch cannot be omitted')
        item['relative_to_both_diagonals']=max(item['frobenius_norm']/norms[p],item['frobenius_norm']/norms[q]) if p!=q else 0.0
        item['passed']=(item.get('authority_relative_difference',0)<=1e-11 and item['relative_to_both_diagonals']<=1e-11)
    result={'diagonal_blocks':diagonal,'all_block_pairs':pairs,'passed':all(v['passed'] for v in pairs),
            'numeric_factor_count':0,'candidate_local_or_global_S_created':False,'q_factors_permitted':False}
    event('quotient_complete_operator_audit',result)
    if not result['passed']:raise ValueError('raw/stored quotient operator identity failed; no cutoff relaxation')
    return result
