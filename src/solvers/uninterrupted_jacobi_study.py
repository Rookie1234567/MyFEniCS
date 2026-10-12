"""Read-only Jacobi reuse on the existing controlled solve and audit tail."""
import numpy as np

from src.runners.task042_shared import write_json
from . import uninterrupted_jacobi_scope as scope
from .scattering_anchor import Journal
from .scattering_anchor_checks import checked_arrays


def diagonal_parent():
    from . import controlled_trace_scope as old
    record=scope.checked_json(scope.plan_record()['jacobi_parent'])
    if not record['pass_gate'] or record['exact_zero_diagonals']!=0:
        raise ValueError('V76 immutable diagonal mathematical qualification')
    for key in ('local_packet','boundary_arrays'):
        if old.plan_record()['prepared_parent'][key]!=scope.plan_record()['prepared_parent'][key]:
            raise ValueError('Jacobi original operator/complete boundary identity')
    return record


def precheck(folder,journal):
    parent=diagonal_parent()
    with journal.measured('readonly_qualified_diagonal_RHS_scales'):
        d=checked_arrays(parent['diagonal']); r=checked_arrays(parent['physical_rhs'])
    if len(d['diagonal'])!=1177293 or not all(np.isfinite(v).all() for v in d.values()):
        raise ValueError('Jacobi array inventory/finite')
    zero=int(np.count_nonzero(d['diagonal']==0))
    inverse_error=float(np.max(np.abs(d['inverse']*d['diagonal']-1)))
    if zero or inverse_error>1e-14 or any(not np.array_equal(d[k],r[k]) for k in ('left','right')):
        raise ValueError('Jacobi inverse and original RHS coordinate identity')
    p=scope.plan_record()['prepared_parent']['local_packet']
    # Manifest/member checking remains in the original packet reader at solve;
    # preflight binds its public manifest without replaying operator witnesses.
    scope.checked_json(p)
    result=dict(status='COMPLETED',pass_gate=True,diagonal=parent['diagonal'],
        physical_rhs=parent['physical_rhs'],parent=scope.plan_record()['jacobi_parent'],
        packet=p,inverse_operation_error=inverse_error,exact_zero_diagonals=zero,
        actual_rows=len(d['diagonal']),new_diagonal_constructions=0,new_global_actions=0,
        new_numeric_factors=0,new_complete_solves=0,global_fine_K_reads=0,global_fine_S_reads=0,
        source=journal.source_state,timings=journal.timings)
    write_json(folder/'readonly_jacobi_precheck.json',result)
    return result


def pc_factory(*,left,right,full_rhs,scaled_rhs,**context):
    from .controlled_trace_study import SimplePC
    record=scope.stage('PRECHECK'); d=checked_arrays(record['diagonal']); r=checked_arrays(record['physical_rhs'])
    if any(not np.array_equal(d[k],v) for k,v in [('left',left),('right',right)]) or not np.array_equal(r['full_rhs'],full_rhs) or not np.array_equal(r['bhat'],scaled_rhs):
        raise ValueError('live original RHS/scale matches qualified Jacobi parent')
    return SimplePC(d['inverse']),0


def execute(role,folder,state):
    if state.get('memory_budget')!=scope.memory_budget(role): raise ValueError('V78 live resolved budget')
    journal=Journal(folder,window_scope=scope.window,planning_limit_bytes=64*2**30)
    journal.source_state=state
    if role=='PRECHECK': return precheck(folder,journal)
    if role in scope.SOLVES:
        from .controlled_trace_study import iterate,consume_returned
        if state.get('postprocessing_resume'): return consume_returned(role,folder,journal,state,scope=scope)
        return iterate(role,folder,journal,state,scope=scope,pc_factory=pc_factory,
            strategy='J128_CONTINUOUS',iteration_policy=scope.iteration_policy())
    if role=='VERIFY_COST':
        from benchmarks.collect_controlled_trace import verify
        return verify(folder,journal,scope=scope)
    raise ValueError('V78 explicit one-run role')
