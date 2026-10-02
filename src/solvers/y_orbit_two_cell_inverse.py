"""Opt-in complete native inverse using every audited two-cell branch.

Full original FE coordinates remain the outer equation. No full-Ny S/F/Q is
created. Primal lifts and dual folds are distinct for native moment bases.
"""
from __future__ import annotations

from time import perf_counter
import numpy as np
from scipy.sparse.linalg import splu

from .y_orbit_sparse_reference import _gate, csr_audit, sparse_hash


class StreamedFullYLayout:
    """Entity moment blocks and the bounded small Ny cell-index DFT."""
    def __init__(self,entities,cfg,*,direct_profile=None):
        if direct_profile is None:
            ny_expected, width_expected, independent_expected = 4, 3968, 15872
        else:
            from .y_orbit_direct_profile import validate_direct_physical_config
            profile = validate_direct_physical_config(cfg, direct_profile)
            ny_expected, width_expected, independent_expected = profile.ny, profile.rows_per_q, profile.independent_rows
            if entities.full_rows != profile.storage_rows or getattr(entities, '_transform_bank', None) is None:
                raise ValueError('direct full layout requires complete shared-bank native storage')
        if entities.ny!=ny_expected or entities.width!=width_expected or len(entities.independent)!=independent_expected:
            raise ValueError('bounded same80 full p4 native layout required')
        self.entities=entities;self.independent=entities.independent
        self.full_rows=entities.full_rows;self.ny=entities.ny;self.width=entities.width
        self.independent_rows=len(entities.independent)
        self.direct_profile_name=None if direct_profile is None else profile.name
        self.phase_y=complex(cfg.floquet_phase_y)
        theta=(complex(cfg.ky).real*float(cfg.period_y)+2*np.pi*np.arange(self.ny))/self.ny
        self.cell_dft=np.exp(1j*np.arange(self.ny)[:,None]*theta[None,:])/np.sqrt(self.ny)
        if (abs(complex(cfg.ky).imag)>1e-12 or abs(abs(self.phase_y)-1)>1e-12
                or np.linalg.norm(self.cell_dft.conj().T@self.cell_dft-np.eye(self.ny))>1e-12):
            raise ValueError('real Bloch phase and complete unitary cell-index DFT required')
        self.audit={'full_storage_rows':self.full_rows,'independent_rows':self.independent_rows,'ny':self.ny,
                    'all_q':list(range(self.ny)),'rows_per_q':self.width,'full_F_Q_created':False,
                    'raw_native_unitarity_assumed':False,'small_cell_DFT_shape':[self.ny,self.ny]}

    def _dft(self,values,*,adjoint):
        values=np.asarray(values,dtype=complex)
        if values.shape!=(self.independent_rows,) or not np.isfinite(values).all():raise ValueError('complete finite full FE vector required')
        matrix=self.cell_dft.conj().T if adjoint else self.cell_dft
        return (matrix@values.reshape(self.ny,self.width)).reshape(-1)

    def dual_to_modal(self,rhs):
        return self._dft(self.entities.transform(rhs,direction='dual_to_canonical'),adjoint=True)

    def primal_to_modal(self,solution):
        return self._dft(self.entities.transform(solution,direction='primal_to_canonical'),adjoint=True)

    def primal_from_modal(self,values):
        return self.entities.transform(self._dft(values,adjoint=False),direction='primal_from_canonical')

    def modal_norms(self,values,*,dual):
        modal=self.dual_to_modal(values) if dual else self.primal_to_modal(values)
        return [float(np.linalg.norm(v)) for v in modal.reshape(self.ny,self.width)]


class FourBranchFactors:
    """Sequential public SuperLU factors, all actual q retained; unknown fill.

    The declared allowance is a policy for admission, not a memory prediction.
    Current RSS already contains previously retained factors and both caches.
    """
    def __init__(self,matrices,*,allocation_gate,event,save_array,direct_profile=None):
        if direct_profile is None:
            self.nq, self.row_counts, self.per_q_allowance = 4, (1884,1960,1960,1960), 128*1024**2
            self.direct_profile_name = None
        else:
            from .y_orbit_direct_profile import direct_profile_metadata
            profile = direct_profile_metadata(direct_profile)
            self.nq, self.row_counts, self.per_q_allowance = profile.ny, profile.augmented_rows_per_q, profile.factor_allowance_per_q_bytes
            self.direct_profile_name = profile.name
        if set(matrices)!=set(range(self.nq)):raise ValueError('all actual q branches required before factors')
        if direct_profile is not None:
            for q in range(self.nq):
                if matrices[q].shape != (self.row_counts[q], self.row_counts[q]):
                    raise ValueError('every direct profile q shape must be verified before the first factor')
                csr_audit(matrices[q], petsc_index_dtype=matrices[q].indices.dtype)
        self.gate,self.event,self.save=allocation_gate,event,save_array
        self.factors={};self.calls=0;self.destroyed=False;self.audit={'input_blocks':[],'tests':[]}
        started=perf_counter()
        try:
            for q in range(self.nq):
                matrix=matrices[q];facts=csr_audit(matrix,petsc_index_dtype=matrix.indices.dtype)
                if matrix.shape!=(self.row_counts[q],self.row_counts[q]):
                    raise ValueError('complete fixed p4 trace/alias dimensions differ')
                payload=int(matrix.data.nbytes+matrix.indices.nbytes+matrix.indptr.nbytes)
                remaining=(self.nq-len(self.factors))*self.per_q_allowance
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
                    'factor_memory_bytes':None,'remaining_declared_allowance_bytes':(self.nq-len(self.factors))*self.per_q_allowance})
            self.audit.update(setup_seconds=perf_counter()-started,all_q_factors=self.nq,
                              factor_reuse_plus_minus_q=False,factor_L_U_copies=False,
                              all_reformed_blocks_compared_before_factor=True,
                              all_four_retained_simultaneously=True)
            if direct_profile is not None:
                if self.nq != 4:self.audit.pop('all_four_retained_simultaneously')
                self.audit.update(all_actual_q_retained_simultaneously=True,
                                  factor_allowance_aggregate_bytes=self.nq*self.per_q_allowance,
                                  resource_policy='unchanged_128MiB_per_q; Y_768MiB_aggregate_requires_review_before_numeric',
                                  direct_profile=self.direct_profile_name)
        except BaseException:
            self.destroy();raise

    def solve(self,q,rhs):
        if self.destroyed or set(self.factors)!=set(range(self.nq)):raise RuntimeError('all four live factors required')
        rhs=np.asarray(rhs,dtype=complex)
        if self.direct_profile_name is not None and (type(q) is not int or q not in range(self.nq)):
            raise ValueError('actual q index required')
        expected=self.row_counts[q]
        if rhs.shape!=(expected,) or not np.isfinite(rhs).all():raise ValueError('complete finite augmented branch RHS required')
        result=self.factors[q].solve(rhs)
        if not np.isfinite(result).all():raise FloatingPointError('branch factor returned nonfinite values')
        self.calls+=1;return result

    def destroy(self):
        self.factors.clear();self.destroyed=True


class CompleteTwoCellInverse:
    """Borrow every complete local recovery bundle and all actual q factors."""
    def __init__(self,sectors,full_layout,factors,*,allocation_gate,direct_profile=None):
        if direct_profile is None:
            replication_count, independent_rows, local_storage_rows = 2, 15872, 8940
        else:
            from .y_orbit_direct_profile import direct_profile_metadata
            profile = direct_profile_metadata(direct_profile)
            replication_count, independent_rows, local_storage_rows = profile.replication_count, profile.independent_rows, profile.local_storage_rows
            if full_layout.direct_profile_name != profile.name or factors.direct_profile_name != profile.name:
                raise ValueError('direct inverse layout/factors/profile identity differs')
            if any(s['context'].direct_profile_name != profile.name
                   or s['transport'].full is not full_layout.entities
                   or s['transport'].local._transform_bank is not full_layout.entities._transform_bank
                   for s in sectors):
                raise ValueError('every direct inverse sector must retain profile identity')
        if len(sectors)!=replication_count or [s['context'].twist_index for s in sectors]!=list(range(replication_count)):
            raise ValueError('two ordered twists and every original mode required')
        union=sorted(i for s in sectors for i in s['context'].original_mode_indices)
        if union!=list(range(532)):raise ValueError('all original ports must survive exactly once')
        self.sectors,self.layout,self.factors,self.gate=sectors,full_layout,factors,allocation_gate
        self.independent_rows, self.local_storage_rows, self.K = independent_rows, local_storage_rows, replication_count
        self.calls=0;self.last_port_solution=None;self.last_local_solutions=None

    def apply_augmented(self,rhs,port_rhs=None):
        rhs=np.asarray(rhs,dtype=complex)
        ports=np.zeros(532,complex) if port_rhs is None else np.asarray(port_rhs,dtype=complex)
        if rhs.shape!=(self.independent_rows,) or ports.shape!=(532,) or not np.isfinite(rhs).all() or not np.isfinite(ports).all():
            raise ValueError('complete full original FE and auxiliary RHS required')
        _gate(self.gate,'complete_full3D_dual_fold_recovery',payload=(12*self.independent_rows+12*self.local_storage_rows)*16,
              workspace=16<<20,all_interior_and_alias_channels=True)
        result=np.zeros(self.independent_rows,complex);alpha=np.empty(532,complex);local_solutions=[]
        for sector in self.sectors:
            transport=sector['transport'];condensed=sector['condensed'];coords=sector['coordinates']
            context=sector['context'];ids=np.asarray(context.original_mode_indices,dtype=np.int64)
            local_rhs=np.zeros(self.local_storage_rows,complex)
            local_rhs[condensed.independent_original_rows]=transport.fold_dual(rhs)
            local_port_rhs=ports[ids]/np.sqrt(2) if self.K==2 else ports[ids]/np.sqrt(self.K)
            reduced=condensed.reduce_rhs(local_rhs,port_rhs=local_port_rhs,rhs_is_mpc_dual=True)
            native=np.zeros(condensed.action.reduced_size,complex)
            for branch in (0,1):
                q=context.global_q_indices[branch];qm=coords.q_map(branch)
                modal=np.asarray(qm.conj().T@reduced)
                native+=qm@self.factors.solve(q,modal)
            recovered=condensed.recover_storage(native,full_rhs=local_rhs,expand_trace=False)
            result+=transport.lift_primal(recovered[condensed.independent_original_rows])
            alpha[ids]=native[condensed.system.active_rows:]/np.sqrt(self.K)
            local_solutions.append({'twist':context.twist_index,'FE_rhs':local_rhs,
                                    'port_rhs':local_port_rhs,'reduced_solution':native,
                                    'recovered_storage':recovered})
        if not np.isfinite(result).all() or not np.isfinite(alpha).all():raise FloatingPointError('full original recovery is nonfinite')
        self.last_port_solution=alpha;self.last_local_solutions=local_solutions;self.calls+=1
        return result,alpha

    def apply_array(self,rhs):return self.apply_augmented(rhs)[0]

    def apply(self,_pc,source,target):target.array[:]=self.apply_array(source.getArray(readonly=True))
