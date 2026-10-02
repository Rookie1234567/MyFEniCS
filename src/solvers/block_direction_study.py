"""Original-packet qualification and the single three-residual V25 batch."""
from time import perf_counter
import numpy as np
from src.io import block_direction_diagnostic as io
from src.solvers.block_residual_direction import diagnose,decision,relative
from src.solvers.local_block_study import load_local
from src.solvers.local_block_readiness import local_readiness
from src.solvers.local_block_coarse import ROWS
from src.solvers.neural_fe_action_packet import array_hash
from src.solvers.augmented_trace_lsqr import BarAction
from src.solvers.stable_head_varpro import PortBlocks
from src.solvers.fixed_p3_ilu0 import direct_C
from src.runners.orthonormal_trace_reprofile import atomic_arrays
from src.runners.task042_shared import write_json


def run(stage):
    packet=stage.packet;own=stage.own_plan
    if (packet.nt,packet.np,packet.size)!=(18144,40,18184):raise ValueError('V25 trace/port inventory')
    if array_hash(packet.a['masters'])!=own['canonical_master_sha256'] or array_hash(packet.a['b'])!=own['b_sha256']:
        raise ValueError('V25 canonical master/physical RHS hash')
    setup=io.checked_json(own['local_setup'],io.ROOT/'benchmarks/artifacts/task042/v24')
    if setup['source_sha']!=own['upstream_source_sha'] or setup['operator_packet']['sha256']!=own['action_sha256']:
        raise ValueError('V25 local source/operator differs')
    admission=local_readiness(setup,expected_map=own['map'])
    if not admission['qualified']:return dict(status='NOT_RUN',reason='LOCAL_READY_GATE',admission=admission)
    payload=sum(2*int(n)**2*16+int(n)*4 for n in ROWS)
    planned=4*2**30+payload+max(ROWS)**2*16+12*packet.nt*8*16
    if payload>2*2**30 or planned>8*2**30:raise MemoryError('V25 simultaneous preallocation plan')
    stage.meta.update(simultaneous_planned_bytes=planned,planning_role='derived; not RSS',
        local_explicit_payload_bytes=payload,local_factors_present=True,local_factors_rebuilt=False,
        local_ready_evidence=admission,upstream_source_sha=own['upstream_source_sha'])
    started=perf_counter()
    local,reloaded=load_local(stage,setup,factor_root=io.ROOT/'benchmarks/artifacts/task042/v24/blocks')
    factor_reader_seconds=perf_counter()-started
    # This constructs original forty columns directly from the packet tensors,
    # not by 40 additional S probes, and does not read any old coarse arrays.
    C=np.column_stack([direct_C(packet,np.eye(40,dtype=complex)[:,j]) for j in range(40)])
    columns=np.vstack((C,packet.a['Hhat']))
    ports=PortBlocks(packet,columns);stage.pc_count('port_factors');bar=BarAction(ports)
    solve=bar.solve_port;last_port=[np.zeros(40,complex)]
    def port_solve(rhs,adjoint=False):
        stage.pc_count('port_solves');value=solve(rhs,adjoint=adjoint)
        last_port[0]=value;return value
    bar.solve_port=port_solve
    # Bound the sizes of contractions before cancellation, without another
    # original action or a global matrix. Duplicate E entries are bounded by
    # their absolute sum, rather than dropped or assumed orthogonal.
    a=packet.a
    e_bound=np.bincount(a['erows']//packet.lt,weights=np.abs(a['evals']),minlength=packet.nc)
    s_norm=np.linalg.norm(a['S'],axis=(1,2))[a['classes']]
    Cnorm=float(np.linalg.norm(C))
    def scale(q):
        return float(np.dot(e_bound*s_norm,np.linalg.norm(packet._expand(q),axis=1))+Cnorm*np.linalg.norm(last_port[0]))
    rhs=a['b'];barb=bar.reduced_rhs(rhs);rows=[]
    result=dict(status='DIAGNOSTIC_COMPLETE',rows=rows,independent_factor_reload=reloaded,
        factor_reader_seconds=factor_reader_seconds,port_H_condition=ports.cond_H,
        port_Hhat_sha256=array_hash(ports.H),original_C_sha256=array_hash(C),
        new_assembly=0,new_local_factor=0,no_new_solver_state=True,reference_read=False,
        read_member_whitelist=['trace','port','z','residual'],decision='PENDING')
    stage.partial_result=result
    for item in own['states']:
        stage.guard();name=item['name'];parent=io.checked_json(item['parent_result'],io.ROOT/'benchmarks/artifacts/task042/v24')
        if parent['source_sha']!=own['upstream_source_sha'] or parent['operator_packet']['sha256']!=own['action_sha256']:
            raise ValueError('V25 cold parent source/action identity')
        state=parent['start'] if name.endswith('INITIAL') else parent['cycles'][3]
        if state['state']!=item['state']:raise ValueError('V25 exact frozen state differs')
        values=io.physical_state(item,packet);trace=values['trace']
        closed=bar.close(trace,rhs)
        residual=rhs-packet.apply(values['z'])
        r=barb-bar.apply(trace)
        iddiff=float(np.linalg.norm(r-values['residual'][:packet.nt])/packet.bnorm)
        full_diff=float(np.linalg.norm(residual-values['residual'])/packet.bnorm)
        port_diff=float(np.linalg.norm(closed[packet.nt:]-values['port'])/(1+np.linalg.norm(values['port'])))
        port_full=float(np.linalg.norm(residual[packet.nt:])/packet.bnorm)
        port_scale=float(np.linalg.norm(ports.H@values['port'])+np.linalg.norm(rhs[packet.nt:])+np.linalg.norm(rhs[packet.nt:]-ports.H@values['port']-residual[packet.nt:]))
        port_op=relative(float(np.linalg.norm(residual[packet.nt:])),port_scale)
        identity=dict(saved_trace_residual_full_b_relative=iddiff,saved_full_residual_full_b_relative=full_diff,
            reclosed_port_operation_relative=port_diff,port_full_rhs_relative=port_full,port_operation_relative=port_op,
            full_b_norm=packet.bnorm,trace_residual_norm=float(np.linalg.norm(r)),
            physical_state_member_hashes={k:item['state'][k+'_sha256'] for k in ('trace','port','z','residual')},
            cold_initial_port_norm=float(np.linalg.norm(values['port'])),homogeneous_direction_rhs=True,
            internal_particular_solution_not_applied_to_directions=True)
        if max(iddiff,full_diff)>1e-11 or port_diff>1e-10 or port_full>1e-10 or port_op is None or port_op>1e-10:
            raise ValueError('V25 saved residual/port identity Gate: '+repr(identity))
        metrics,arrays=diagnose(r,local,bar.apply,bnorm=packet.bnorm,operation_scale=scale,count=stage.pc_count,guard=stage.guard)
        receipt=atomic_arrays(stage.artifact/(name+'.npz'),**arrays)
        row=dict(name=name,input_state=item['state'],identity=identity,**metrics,diagnostic_arrays=receipt)
        rows.append(row);write_json(stage.artifact/(name+'.json'),row)
        stage.event('frozen_residual_diagnosed',name=name,status=row['status'],eta_unit=row['eta_unit'],eta1=row['eta1'],eta8=row['eta8'])
    result.update(decision=decision(rows),status='DIAGNOSTIC_COMPLETE' if all(r['trustworthy'] for r in rows) else 'NUMERICALLY_UNRESOLVED',
        local_apply_seconds=local.seconds,local_solve_seconds=local.solve_seconds,port_seconds=bar.costs,
        cost_timers_nested=True,neural_20percent_increment='NOT_DEMONSTRATED')
    return result
