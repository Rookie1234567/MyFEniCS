"""Opt-in complete native inverse using all four audited two-cell branches.

Full original FE coordinates remain the outer equation. No full-Ny S/F/Q is
created. Primal lifts and dual folds are distinct for native moment bases.
"""
from __future__ import annotations

from time import perf_counter
import numpy as np
from scipy.sparse.linalg import splu

from .y_orbit_sparse_reference import _gate, csr_audit, sparse_hash


class StreamedFullYLayout:
    """Entity moment blocks and a 4x4 cell-index DFT, not a full FE map."""
    def __init__(self,entities,cfg):
        if entities.ny!=4 or entities.width!=3968 or len(entities.independent)!=15872:
            raise ValueError('bounded same80 full p4 native layout required')
        self.entities=entities;self.independent=entities.independent
        self.full_rows=entities.full_rows;self.ny=4;self.width=entities.width
        self.phase_y=complex(cfg.floquet_phase_y)
        theta=(complex(cfg.ky).real*float(cfg.period_y)+2*np.pi*np.arange(4))/4
        self.cell_dft=np.exp(1j*np.arange(4)[:,None]*theta[None,:])/2
        if (abs(complex(cfg.ky).imag)>1e-12 or abs(abs(self.phase_y)-1)>1e-12
                or np.linalg.norm(self.cell_dft.conj().T@self.cell_dft-np.eye(4))>1e-12):
            raise ValueError('real Bloch phase and complete unitary cell-index DFT required')
        self.audit={'full_storage_rows':self.full_rows,'independent_rows':15872,'ny':4,
                    'all_q':[0,1,2,3],'rows_per_q':3968,'full_F_Q_created':False,
                    'raw_native_unitarity_assumed':False,'small_cell_DFT_shape':[4,4]}

    def _dft(self,values,*,adjoint):
        values=np.asarray(values,dtype=complex)
        if values.shape!=(15872,) or not np.isfinite(values).all():raise ValueError('complete finite full FE vector required')
        matrix=self.cell_dft.conj().T if adjoint else self.cell_dft
        return (matrix@values.reshape(4,3968)).reshape(-1)

    def dual_to_modal(self,rhs):
        return self._dft(self.entities.transform(rhs,direction='dual_to_canonical'),adjoint=True)

    def primal_to_modal(self,solution):
        return self._dft(self.entities.transform(solution,direction='primal_to_canonical'),adjoint=True)

    def primal_from_modal(self,values):
        return self.entities.transform(self._dft(values,adjoint=False),direction='primal_from_canonical')

    def modal_norms(self,values,*,dual):
        modal=self.dual_to_modal(values) if dual else self.primal_to_modal(values)
        return [float(np.linalg.norm(v)) for v in modal.reshape(4,3968)]


class FourBranchFactors:
    """Sequential public SuperLU factors, all four retained; unknown fill.

    The declared allowance is a policy for admission, not a memory prediction.
    Current RSS already contains previously retained factors and both caches.
    """
    def __init__(self,matrices,*,allocation_gate,event,save_array):
        if set(matrices)!=set(range(4)):raise ValueError('all four branches required before factors')
        self.gate,self.event,self.save=allocation_gate,event,save_array
        self.factors={};self.calls=0;self.destroyed=False;self.audit={'input_blocks':[],'tests':[]}
        started=perf_counter()
        try:
            for q in range(4):
                matrix=matrices[q];facts=csr_audit(matrix,petsc_index_dtype=matrix.indices.dtype)
                if matrix.shape!=((1884,1884) if q==0 else (1960,1960)):
                    raise ValueError('complete fixed p4 trace/alias dimensions differ')
                payload=int(matrix.data.nbytes+matrix.indices.nbytes+matrix.indptr.nbytes)
                remaining=(4-len(self.factors))*128*1024**2
                _gate(self.gate,'quotient_factor_q_'+str(q),payload=3*payload,
                      workspace=2*payload,evidence_reserve_bytes=128*1024**2,
                      factor_workspace_allowance_bytes=remaining,
                      retained_factor_count=len(self.factors),factor_fill_prediction=None,
                      LU_fill_and_workspace_unknown=True)
                digest=sparse_hash(matrix)
                csc=matrix.tocsc();begin=perf_counter();factor=splu(csc)
                self.factors[q]=factor
                self.event('all_branch_factor_created',{'q':q,'factor_count':len(self.factors),
                           'retained_factor_count':len(self.factors),'input_CSR_sha256':digest})
                j=np.arange(matrix.shape[0]);a=np.cos(.23*j)+1j*np.sin(.37*j)
                b=np.sin(.29*j)+1j*np.cos(.41*j)
                x=factor.solve(a);repeat=factor.solve(a);y=factor.solve(b);combined=factor.solve(a+b)
                # Save actual inputs/results before assertions, including any
                # nonfinite failure data supported by the bounded writer.
                for name,value in (('rhs_a',a),('rhs_b',b),('solution_a',x),('solution_a_repeat',repeat),
                                   ('solution_b',y),('solution_sum',combined),('action_a',matrix@x)):
                    self.save(f'q_{q}_'+name,value)
                residual=max(float(np.linalg.norm(matrix@x-a)/np.linalg.norm(a)),
                             float(np.linalg.norm(matrix@y-b)/np.linalg.norm(b)))
                repeated=float(np.linalg.norm(repeat-x)/max(np.linalg.norm(x),np.finfo(float).tiny))
                linear=float(np.linalg.norm(combined-x-y)/max(np.linalg.norm(combined),np.finfo(float).tiny))
                test={'q':q,'true_block_residual':residual,'repeated_difference':repeated,
                      'linearity_difference':linear,'limit_residual':1e-10,'limit_linear':1e-11}
                from .dtn_boundary_plane_qualification import _failure_diagnostic
                self.audit['tests'].append(test);self.event('all_branch_factor_test',_failure_diagnostic(test))
                if (not all(np.isfinite(v) for v in (residual,repeated,linear))
                        or residual>1e-10 or max(repeated,linear)>1e-11):
                    raise ValueError('factor original block/repeat/linearity gate failed')
                if sparse_hash(matrix)!=digest:raise ValueError('factor mutated its bound input CSR')
                self.audit['input_blocks'].append({'q':q,'shape':list(matrix.shape),'nnz':int(matrix.nnz),
                    'CSR_sha256':digest,'factor_seconds':perf_counter()-begin,'CSR_payload_bytes':payload,
                    'factor_memory_bytes':None,'public_backend':'scipy.sparse.linalg.splu',**facts})
                del csc
                self.event('all_branch_factor_retained',{'q':q,'retained_factor_count':len(self.factors),
                    'factor_memory_bytes':None,'remaining_declared_allowance_bytes':(4-len(self.factors))*128*1024**2})
            self.audit.update(setup_seconds=perf_counter()-started,all_q_factors=4,
                              factor_reuse_plus_minus_q=False,factor_L_U_copies=False,
                              all_reformed_blocks_compared_before_factor=True,
                              all_four_retained_simultaneously=True)
        except BaseException:
            self.destroy();raise

    def solve(self,q,rhs):
        if self.destroyed or set(self.factors)!=set(range(4)):raise RuntimeError('all four live factors required')
        rhs=np.asarray(rhs,dtype=complex)
        expected=1884 if q==0 else 1960
        if rhs.shape!=(expected,) or not np.isfinite(rhs).all():raise ValueError('complete finite augmented branch RHS required')
        result=self.factors[q].solve(rhs)
        if not np.isfinite(result).all():raise FloatingPointError('branch factor returned nonfinite values')
        self.calls+=1;return result

    def destroy(self):
        self.factors.clear();self.destroyed=True


class CompleteTwoCellInverse:
    """Borrow both complete local recovery bundles and all four factors."""
    def __init__(self,sectors,full_layout,factors,*,allocation_gate):
        if len(sectors)!=2 or [s['context'].twist_index for s in sectors]!=[0,1]:
            raise ValueError('two ordered twists and every original mode required')
        union=sorted(i for s in sectors for i in s['context'].original_mode_indices)
        if union!=list(range(532)):raise ValueError('all original ports must survive exactly once')
        self.sectors,self.layout,self.factors,self.gate=sectors,full_layout,factors,allocation_gate
        self.calls=0;self.last_port_solution=None;self.last_local_solutions=None

    def apply_augmented(self,rhs,port_rhs=None):
        rhs=np.asarray(rhs,dtype=complex)
        ports=np.zeros(532,complex) if port_rhs is None else np.asarray(port_rhs,dtype=complex)
        if rhs.shape!=(15872,) or ports.shape!=(532,) or not np.isfinite(rhs).all() or not np.isfinite(ports).all():
            raise ValueError('complete full original FE and auxiliary RHS required')
        _gate(self.gate,'complete_full3D_dual_fold_recovery',payload=(12*15872+12*8940)*16,
              workspace=16<<20,all_interior_and_alias_channels=True)
        result=np.zeros(15872,complex);alpha=np.empty(532,complex);local_solutions=[]
        for sector in self.sectors:
            transport=sector['transport'];condensed=sector['condensed'];coords=sector['coordinates']
            context=sector['context'];ids=np.asarray(context.original_mode_indices,dtype=np.int64)
            local_rhs=np.zeros(8940,complex)
            local_rhs[condensed.independent_original_rows]=transport.fold_dual(rhs)
            reduced=condensed.reduce_rhs(local_rhs,port_rhs=ports[ids]/np.sqrt(2),rhs_is_mpc_dual=True)
            native=np.zeros(condensed.action.reduced_size,complex)
            for branch in (0,1):
                q=context.global_q_indices[branch];qm=coords.q_map(branch)
                modal=np.asarray(qm.conj().T@reduced)
                native+=qm@self.factors.solve(q,modal)
            recovered=condensed.recover_storage(native,full_rhs=local_rhs,expand_trace=False)
            result+=transport.lift_primal(recovered[condensed.independent_original_rows])
            alpha[ids]=native[condensed.system.active_rows:]/np.sqrt(2)
            local_solutions.append({'twist':context.twist_index,'FE_rhs':local_rhs,
                                    'port_rhs':ports[ids]/np.sqrt(2),'reduced_solution':native,
                                    'recovered_storage':recovered})
        if not np.isfinite(result).all() or not np.isfinite(alpha).all():raise FloatingPointError('full original recovery is nonfinite')
        self.last_port_solution=alpha;self.last_local_solutions=local_solutions;self.calls+=1
        return result,alpha

    def apply_array(self,rhs):return self.apply_augmented(rhs)[0]

    def apply(self,_pc,source,target):target.array[:]=self.apply_array(source.getArray(readonly=True))
