"""Audit-only streamed two-cell augmented branch matrices; no q factor API."""
from __future__ import annotations

import numpy as np
from scipy import sparse

from .y_orbit_sparse_reference import integer_admission, csr_audit, _gate


class TwoCellBranchCoordinates:
    def __init__(self, trace, condensed, context, *, global_original_H, allocation_gate, index_dtype):
        self.trace,self.context,self.index_dtype=trace,context,np.dtype(index_dtype)
        self.gate=allocation_gate
        self.width=int(trace['trace_width']);self.trace_rows=int(condensed.system.active_rows)
        self.ports=len(condensed.action_bundle['modes']);self.rows=self.trace_rows+self.ports
        if trace['ny']!=2 or self.width!=1808 or self.trace_rows!=3616 or self.ports not in (228,304):
            raise ValueError('fixed complete two40 p4 trace/port inventory required')
        carrier=condensed.action_bundle['dtn_action'].carrier
        h=np.asarray([e.normalization_h for e in carrier.entries])
        global_h=np.asarray(global_original_H)[np.asarray(context.original_mode_indices)]
        if (h.shape!=global_h.shape or np.any(h<=0) or not np.isfinite(h).all()
                or np.max(np.abs(h-global_h/2)/h)>1e-12):
            raise ValueError('actual local originalH must equal frozen globalH/K per mode')
        self.scale=1/np.sqrt(h)
        branch=np.asarray(context.local_branch_indices)
        self.aliases=tuple(np.flatnonzero(branch==b) for b in (0,1))
        expected=(76,152) if context.twist_index==0 else (152,152)
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
                    'positive_H_coordinates':True,'global_matrices_created':False,'numeric_factor_calls':0}

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
    def __init__(self, condensed, coordinates, *, allocation_gate):
        self.condensed,self.coordinates,self.gate=condensed,coordinates,allocation_gate
        self.calls=0

    def block(self,p,q):
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
