"""Bounded sparse analysis for the single authorized V51 h increment.

The dense global envelope remains recorded. Assembly has its own conservative
graph/cache envelope. Numeric admission then requires the existing MUMPS
symbolic estimate with a factor of two plus all live tree objects and a
separate two-GiB future-workspace reserve. No ordering or fill scan.
"""
import os
from .scattering_accuracy import capacity as dense_capacity


def h_capacity(setup,cfg,journal):
    dense=dense_capacity(setup,cfg,journal)
    V=setup['spaces'][cfg.nedelec_degree];nc=dense['cells'];dim=V.element.space_dimension
    local_trace=dim-len(V.element.basix_element.entity_dofs[3][0]);nt=dense['trace'];n=dense['native'];nm=532
    # MPI1 envelope MPC is a single unit master per slave: expansion does not
    # enlarge the cell graph. Duplicate cell contributions remain included.
    coefficients,offsets=setup['floquets'][cfg.nedelec_degree].mpc.coefficients()
    slaves=setup['floquets'][cfg.nedelec_degree].mpc.slaves
    if any(int(offsets[s+1]-offsets[s])!=1 for s in slaves):
        raise ValueError('assembly graph envelope requires single-master periodic MPC')
    graph_nnz=nc*local_trace**2+2*nt*nm+nm**2
    components={
        'all_cell_raw_LU_recovery_conservative':nc*dim**2*16*3,
        'four_sparse_graph_value_index_envelopes':4*(graph_nnz*24+(dense['rows']+1)*8),
        'three_full_native_port_functional_envelopes':3*2*n*nm*16,
        'runtime_mapping_compiler_and_allocator_reserve':2*2**30,
    }
    predicted=sum(components.values())
    result={**dense,'dense_envelope_admitted':dense['admitted'],'dense_envelope_bytes':dense['planned_simultaneous_bytes'],
        'assembly_components_bytes':components,'assembly_graph_nnz_upper':graph_nnz,
        'planned_simultaneous_bytes':predicted,'assembly_only_admitted':dense['rows']<=35000 and predicted<=16*2**30,
        'admitted':dense['rows']<=35000 and predicted<=16*2**30,
        'status':'ASSEMBLY_ONLY_PENDING_SYMBOLIC_NUMERIC_ADMISSION',
        'numeric_rule':'live whole-tree RSS + 2*max(INFOG16,17)*decimal MB + 2GiB future reserve <=16GiB',
        'uncertainty':'engineering prediction, not a continuous RSS guarantee; independent sampled tree24GiB stop unchanged'}
    journal.event('h_assembly_capacity_before_allocation',**result)
    return result


def numeric_plan(rss_bytes,info,limit=16*2**30):
    estimate=max(int(info['infog'][str(k)]) for k in (16,17))
    if estimate<=0:raise ValueError('MUMPS symbolic memory estimate unavailable')
    reserve=2*2**30;allocation=2*estimate*1_000_000;total=int(rss_bytes)+allocation+reserve
    return dict(symbolic_estimate_mb=estimate,numeric_memory_allocation_cap_mb=2*estimate,
        current_whole_tree_rss_bytes=int(rss_bytes),factor_workspace_estimate_times_two_bytes=allocation,
        future_workspace_reserve_bytes=reserve,planned_simultaneous_bytes=total,limit_bytes=limit,
        admitted=total<=limit,estimate_units='decimal MB',classification='symbolic prediction plus bounded allocation, not measured peak')


class AnalyzedDirectFactor:
    """Existing ABI-qualified MUMPS lifecycle, bounded before numeric."""
    def __init__(self,matrix,journal,folder):
        from .fullspace_v17_p3_oracle import _MumpsFactor
        from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
        from src.runners.task042_shared import write_json
        self.journal=journal;self.factor=None;self.backend='PETSc_LU_MUMPS_SYMBOLIC_CAPACITY_BOUNDED'
        factor=_MumpsFactor(matrix)
        try:
            with journal.measured('h_sparse_symbolic_capacity'):
                factor.symbolic(matrix);info=factor.info();sample=process_tree_snapshot(int(os.environ['TASK042_WATCHDOG_PARENT_PID']),'V51-h-symbolic',include_pss=False)
                if sample['rss_bytes'] is None or sample['swap_bytes']!=0:raise MemoryError('symbolic tree RSS/swap identity unavailable')
                if factor.symbolic_memory_settings()['icntl']['22']!=0:raise ValueError('V51 factor must remain in-core; OOC not authorized')
                plan=numeric_plan(sample['rss_bytes'],info)
                write_json(folder/'h_symbolic_capacity.json',dict(info=info,plan=plan,tree=sample,controls=factor.symbolic_memory_settings(),ordering=factor.preferred_ordering))
                if not plan['admitted']:raise MemoryError('h numeric capacity not admitted')
                factor.set_memory_limit_mb(plan['numeric_memory_allocation_cap_mb'])
            with journal.measured('h_bounded_numeric_factor'):
                factor.numeric(matrix)
            write_json(folder/'h_numeric_factor_info.json',dict(info=factor.info(),controls=factor.symbolic_memory_settings(),icntl23_explicitly_bounded=True))
            self.factor=factor
        except BaseException:
            factor.destroy();raise
        journal.event('factor_present',backend=self.backend,factor_class='FINITE_AUTHORITY_EXACT_FACTOR_PRESENT')

    def solve_repeated(self,rhs,target):
        self.journal.calls['factor']+=1;self.factor.solve_repeated(rhs,target)

    def destroy(self):
        if self.factor is not None:self.factor.destroy();self.factor=None
        self.journal.event('global_finite_factor_released')
