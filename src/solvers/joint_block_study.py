"""One qualified joint principal block; two frozen offline cold residuals."""
from pathlib import Path
from time import perf_counter
import numpy as np
from scipy.linalg import lu_solve

from src.io import joint_block_diagnostic as io
from src.solvers.joint_block_direction import (selected_rows,capacity,assemble_selected,
    factor_once,JointSolve,qualification,extra_direction,decision,pair,FACTOR_STATUS,SEEDS)
from src.solvers.local_block_study import mapping
from src.solvers.fixed_p3_ilu0 import direct_C
from src.solvers.stable_head_varpro import PortBlocks
from src.solvers.augmented_trace_lsqr import BarAction
from src.solvers.neural_fe_action_packet import array_hash,file_hash
from src.solvers.p1_image_study import save_array
from src.runners.orthonormal_trace_reprofile import atomic_arrays
from src.runners.task042_shared import write_json


def checked_array(item,allowed):
    p=Path(item['path']).resolve()
    if not p.is_relative_to(allowed) or file_hash(p)!=item['sha256']:raise ValueError('joint read-only file path/hash')
    a=np.load(p,mmap_mode='r',allow_pickle=False)
    if list(a.shape)!=item['shape'] or array_hash(a)!=item['array_sha256'] or a.flags.writeable:raise ValueError('joint array member/shape/mode')
    return a


def cached_directions(item,nt):
    p=Path(item['path']).resolve()
    if not p.is_relative_to(io.ROOT/'benchmarks/artifacts/task042/v25') or file_hash(p)!=item['sha256']:raise ValueError('V25 cache path/hash')
    with np.load(p,allow_pickle=False) as f:a={k:np.array(f[k]) for k in ('directions','images','coefficients')}
    for k,v in a.items():
        if array_hash(v)!=item[k+'_sha256'] or not np.isfinite(v).all():raise ValueError('V25 cache member hash/finite')
    if a['directions'].shape!=a['images'].shape or a['images'].shape!=(nt,8) or a['coefficients'].shape!=(8,):raise ValueError('V25 eight-column shape')
    return a


def run(stage):
    began=perf_counter();packet=stage.packet;own=stage.own_plan
    if (packet.nt,packet.np,packet.size)!=(18144,40,18184):raise ValueError('V26 trace/port inventory')
    if array_hash(packet.a['masters'])!=own['canonical_master_sha256'] or array_hash(packet.a['b'])!=own['b_sha256']:raise ValueError('V26 master/RHS hash')
    setup=io.checked_json(own['local_setup'],io.ROOT/'benchmarks/artifacts/task042/v24')
    if setup['source_sha']!=own['upstream_source_sha'] or setup['operator_packet']['sha256']!=own['action_sha256']:raise ValueError('V26 original local source/action')
    groups,map_check=mapping(stage);ids=selected_rows(groups)
    if array_hash(ids)!=own['joint_rows_sha256']:raise ValueError('pre-registered union order differs')
    plan=capacity(len(ids),packet.nt);write_json(stage.artifact/'capacity_before_allocation.json',plan)
    if not plan['qualified']:raise MemoryError('V26 simultaneous preallocation Gate')
    stage.meta.update(simultaneous_planned_bytes=plan['simultaneous_planned_bytes'],planning_role='derived; not RSS',
        old_eight_LU_loaded=False,old_p1_arrays_loaded=False,joint_blocks=[5,7],joint_rows=3888)
    rows=[];result=dict(status='PENDING',rows=rows,capacity=plan,map_check=map_check,
        source_lineage=dict(V25=own['v25_source_sha'],V24=own['upstream_source_sha']),
        new_solver_states=0,reference_read=False,old_eight_LU_loaded=False,decision='PENDING')
    stage.partial_result=result
    C=np.column_stack([direct_C(packet,np.eye(40,dtype=complex)[:,j]) for j in range(40)])
    started=perf_counter();ports=PortBlocks(packet,np.vstack((C,packet.a['Hhat'])))
    stage.pc_count('port_factors');bar=BarAction(ports);port_setup_seconds=perf_counter()-started
    solve=bar.solve_port;last_port=[np.zeros(40,complex)];port_rhs_inventory=[]
    def port_solve(rhs,adjoint=False):
        stage.pc_count('port_solves');port_rhs_inventory.append(dict(adjoint=adjoint,shape=list(np.shape(rhs)),RHS_columns=1 if np.ndim(rhs)==1 else np.shape(rhs)[1]))
        out=solve(rhs,adjoint=adjoint);last_port[0]=out;return out
    bar.solve_port=port_solve
    result.update(port_H_condition=ports.cond_H,port_setup_seconds=port_setup_seconds,
        port_Hhat_sha256=array_hash(ports.H),original_C_sha256=array_hash(C))
    stage.pc_count('joint_assemblies')
    A,assembly=assemble_selected(packet,ids,C,bar.solve_port,guard=stage.guard,event=stage.event)
    matrix=save_array(stage.artifact/'joint_matrix.npy',A)
    result.update(matrix=matrix,assembly=assembly);write_json(stage.artifact/'matrix_commit.json',result)
    diagonals=[];position=np.full(packet.nt,-1,np.int64);position[ids]=np.arange(len(ids))
    for block in (5,7):
        old=setup['block_inventory'][block];original=checked_array(old['matrix'],io.ROOT/'benchmarks/artifacts/task042/v24/blocks')
        block_ids=np.flatnonzero(groups==block)
        if old['rows']!=block_ids.tolist():raise ValueError('old principal canonical order')
        loc=position[block_ids];check=pair(A[np.ix_(loc,loc)],original)
        if check['operation_relative']>1e-10:raise ValueError('old A5/A7 diagonal identity')
        diagonals.append(dict(block=block,receipt=old['matrix'],**check));del original
    l5,l7=position[np.flatnonzero(groups==5)],position[np.flatnonzero(groups==7)]
    a57=A[np.ix_(l5,l7)];a75=A[np.ix_(l7,l5)]
    result.update(old_diagonal_checks=diagonals,bidirectional_coupling=dict(A57_norm=float(np.linalg.norm(a57)),
        A75_norm=float(np.linalg.norm(a75)),nonmutual=pair(a57,a75.conj().T)));del a57,a75
    factor,safety=factor_once(A,count=stage.pc_count,guard=stage.guard)
    factor_inventory=dict(LU=save_array(stage.artifact/'joint_LU.npy',factor[0]),pivots=save_array(stage.artifact/'joint_pivots.npy',factor[1]))
    result.update(factor_safety=safety,factor_inventory=factor_inventory,factor_status=FACTOR_STATUS)
    stage.meta.update(factor_status=FACTOR_STATUS,new_local_assemblies=1,new_local_factors=1)
    write_json(stage.artifact/'factor_commit.json',result)
    if not safety['qualified']:return dict(result,status='JOINT_FACTOR_UNSAFE',stop_reason='FIXED_RCOND_GATE',dependent_samples='NOT_RUN')
    joint=JointSolve(packet.nt,ids,A,factor,count=stage.pc_count)
    checks=qualification(joint,bar.apply,bar.adjoint);result['joint_checks']=checks
    write_json(stage.artifact/'qualification_commit.json',result)
    if not checks['qualified']:return dict(result,status='JOINT_NUMERICAL_GATE_FAILED',dependent_samples='NOT_RUN')
    # No second LU. Reopen the same files read-only; pivots have their own small
    # writable ABI workspace. This is a reload in this process, not a claim of
    # an independently launched factorization or a new physical solve.
    stage.pc_count('factor_readers');started=perf_counter()
    reloaded_A=checked_array(matrix,stage.artifact);LU=checked_array(factor_inventory['LU'],stage.artifact);piv=checked_array(factor_inventory['pivots'],stage.artifact)
    readonly=JointSolve(packet.nt,ids,reloaded_A,(LU,piv),count=stage.pc_count);reload_checks=[]
    for seed in SEEDS:
        rng=np.random.default_rng(seed);w=rng.standard_normal(len(ids))+1j*rng.standard_normal(len(ids));x=readonly.solve(w)
        error=float(np.linalg.norm(reloaded_A@x-w)/np.linalg.norm(w))
        if error>1e-8:raise ValueError('read-only joint reload solve')
        reload_checks.append(dict(seed=seed,solve_relative=error))
    result['readonly_reload']=dict(qualified=True,witnesses=reload_checks,reader_count=1,independent_process=False,
        refactored=False,factor_readonly=True,private_pivots_bytes=readonly.factor[1].nbytes,seconds=perf_counter()-started)
    result['primary_joint_solve_calls']=joint.calls
    result['primary_joint_solve_seconds']=joint.seconds
    del joint,factor,A;A=reloaded_A;joint=readonly
    a=packet.a;e_bound=np.bincount(a['erows']//packet.lt,weights=np.abs(a['evals']),minlength=packet.nc)
    s_norm=np.linalg.norm(a['S'],axis=(1,2))[a['classes']];Cnorm=float(np.linalg.norm(C))
    def scale(q):return float(np.dot(e_bound*s_norm,np.linalg.norm(packet._expand(q),axis=1))+Cnorm*np.linalg.norm(last_port[0]))
    old_result=io.checked_json(own['v25_result'],io.ROOT/'benchmarks/artifacts/task042/v25')
    from benchmarks.collect_task042_block_direction import fixed_inventory
    old_rows={x['name']:x for x in fixed_inventory(old_result)}
    if old_result['source_sha']!=own['v25_source_sha']:raise ValueError('V25 direction source')
    rhs=a['b'];barb=bar.reduced_rhs(rhs)
    for item in own['states']:
        stage.guard();name=item['name'];values=io.physical_state(item,packet);t=values['trace']
        closed=bar.close(t,rhs);full_residual=rhs-packet.apply(values['z']);r=barb-bar.apply(t)
        identity=dict(saved_trace_residual_full_b_relative=float(np.linalg.norm(r-values['residual'][:packet.nt])/packet.bnorm),
            saved_full_residual_full_b_relative=float(np.linalg.norm(full_residual-values['residual'])/packet.bnorm),
            port_reclosure_operation_relative=float(np.linalg.norm(closed[packet.nt:]-values['port'])/(1+np.linalg.norm(values['port']))),
            port_residual_full_b_relative=float(np.linalg.norm(full_residual[packet.nt:])/packet.bnorm),
            exact_trace_port_z_concat=bool(np.array_equal(values['z'][:packet.nt],t) and np.array_equal(values['z'][packet.nt:],values['port'])),
            internal_particular_solution_applied_to_directions=False)
        if (not identity['exact_trace_port_z_concat'] or max(identity[k] for k in ('saved_trace_residual_full_b_relative','saved_full_residual_full_b_relative'))>1e-11
                or max(identity[k] for k in ('port_reclosure_operation_relative','port_residual_full_b_relative'))>1e-10):raise ValueError('V26 original saved residual/port identity')
        old=old_rows[name]
        if old['diagnostic_arrays']!=item['v25_arrays'] or old['input_state']!=item['state']:raise ValueError('cold state and old cache binding')
        data=cached_directions(item['v25_arrays'],packet.nt)
        metrics,arrays=extra_direction(r,data['directions'],data['images'],data['coefficients'],joint,bar.apply,
            bnorm=packet.bnorm,old_scales=old['operation_scales'],operation_scale=scale,count=stage.pc_count,guard=stage.guard)
        if abs(metrics['eta8']-old['eta8'])>1e-10:raise ValueError('V25 eta8 baseline drift')
        receipt=atomic_arrays(stage.artifact/(name+'.npz'),**arrays)
        row=dict(name=name,input_state=item['state'],old_direction_arrays=item['v25_arrays'],identity=identity,
            **metrics,diagnostic_arrays=receipt);rows.append(row);write_json(stage.artifact/(name+'.json'),row)
        stage.event('joint_extra_direction_diagnosed',name=name,status=row['status'],eta8=row['eta8'],eta9=row['eta9'],g=row['g'])
    result.update(status='DIAGNOSTIC_COMPLETE' if all(x['trustworthy'] for x in rows) else 'NUMERICALLY_UNRESOLVED',
        decision=decision(rows),joint_solve_calls=result['primary_joint_solve_calls']+joint.calls,
        joint_solve_seconds=result['primary_joint_solve_seconds']+joint.seconds,
        port_seconds=bar.costs,port_rhs_inventory=port_rhs_inventory,worker_wall_after_packet_load_seconds=perf_counter()-began,
        cost_timers_nested=True,neural_20percent_increment='NOT_DEMONSTRATED')
    return result
