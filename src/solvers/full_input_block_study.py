"""Two fixed cached inputs, one readonly J bundle, no fitting or iteration."""
from time import perf_counter
import numpy as np
from src.solvers.full_input_block_correction import (NAMES, OUTER_BLOCKS,
    support_inventory, direct_input, certificates, decision)
from src.solvers.return_block_direction import SelectedBundle
from src.solvers.local_block_study import mapping
from src.solvers.local_block_readiness import local_readiness
from src.solvers.joint_block_direction import selected_rows
from src.solvers.fixed_p3_ilu0 import direct_C
from src.solvers.stable_head_varpro import PortBlocks
from src.solvers.augmented_trace_lsqr import BarAction
from src.solvers.neural_fe_action_packet import array_hash
from src.runners.orthonormal_trace_reprofile import atomic_arrays
from src.runners.task042_shared import write_json
from benchmarks.collect_task042_return_direction import load_members


def run(stage):
    io=stage.io; packet=stage.packet; own=stage.own_plan; began=perf_counter()
    if (packet.nt,packet.np,packet.size)!=(18144,40,18184):
        raise ValueError('V33 full original row inventory')
    if (array_hash(packet.a['masters'])!=own['canonical_master_sha256'] or
            array_hash(packet.a['b'])!=own['b_sha256']):
        raise ValueError('V33 canonical master/RHS identity')
    root=io.ROOT/'benchmarks/artifacts/task042'
    setup=io.checked_json(own['local_setup'],root/'v24')
    ready=local_readiness(setup,expected_map=own['map'])
    if (not ready['qualified'] or setup['source_sha']!=own['upstream_source_sha'] or
            setup['operator_packet']['sha256']!=own['action_sha256']):
        raise ValueError('V24 map/setup source/operator seal')
    groups,mapcheck=mapping(stage); ids=selected_rows(groups)
    if array_hash(ids)!=own['joint_rows_sha256']:
        raise ValueError('V33 fixed joint canonical row order')
    prior=io.checked_json(own['v26_result'],root/'v26')
    old=io.checked_json(own['v25_result'],root/'v25')
    ret=io.checked_json(own['v32_result'],root/'v32')
    from benchmarks.collect_task042_block_direction import fixed_inventory
    oldrows={x['name']:x for x in fixed_inventory(old)}
    by26={x['name']:x for x in prior['rows']}; by32={x['name']:x for x in ret['rows']}
    if (len(by26)!=2 or set(by26)!=set(NAMES) or len(by32)!=2 or set(by32)!=set(NAMES)
            or ret['status']!='DIAGNOSTIC_COMPLETE'
            or ret['source_sha']!=own['v32_source_sha']
            or prior['source_sha']!=own['v26_source_sha']
            or old['source_sha']!=own['v25_source_sha']
            or any(p['operator_packet']['sha256']!=own['action_sha256'] for p in (prior,old,ret))):
        raise ValueError('V25/V26/V32 fixed cache/source/operator inventory')
    if not prior['factor_safety']['qualified'] or prior['factor_safety']['rcond1_estimate']<1e-12:
        raise ValueError('V26 original J factor safety')
    one=3888**2*16
    planned=3*2**30+4*one+packet.nt*(40*4+40)*16
    capacity=dict(simultaneous_planned_bytes=planned,qualified=planned<=8*2**30,
        derived_not_RSS=True,J_matrix_and_LU_bytes=2*one,largest_outer_loaded_bytes=0,
        packet_libraries_workspace_allowance_bytes=3*2**30,full_hash_copy=False,
        one_J_reader_only=True,no_new_factor_bytes=True)
    write_json(stage.artifact/'capacity_before_reads.json',capacity)
    if not capacity['qualified']: raise MemoryError('V33 simultaneous planning Gate')
    stage.meta.update(simultaneous_planned_bytes=planned,
        factor_status='READONLY_JOINT_DENSE_LU_PRESENT',selected_old_outer_LU_blocks=[],
        old_eight_LU_loaded=False,old5_7_LU_read=False,full_space_preconditioner=False)
    result=dict(status='PENDING',rows=[],capacity=capacity,map_check=mapcheck,
        factor_readiness=ready,factor_reloads=[],new_solver_states=0,
        new_local_assemblies=0,new_local_factors=0,new_gecon=0,
        operator_identity={k:own[k] for k in ('action_sha256','physical_sha256','mode_sha256','canonical_master_sha256','b_sha256')},
        source_lineage={v:own[k] for v,k in [('V24','upstream_source_sha'),('V25','v25_source_sha'),('V26','v26_source_sha'),('V32','v32_source_sha')]},
        cached_input_diagnostic=True,arbitrary_RHS_PC=False,old5_7_LU_read=False,
        selected_old_outer_LU_blocks=[],decision='PENDING')
    stage.partial_result=result
    C=np.column_stack([direct_C(packet,np.eye(40,dtype=complex)[:,j]) for j in range(40)])
    started=perf_counter(); bar=BarAction(PortBlocks(packet,np.vstack((C,packet.a['Hhat']))))
    stage.pc_count('port_factors'); setup_seconds=perf_counter()-started
    original_solve=bar.solve_port; last_port=[np.zeros(40,complex)]; ports=[]
    def port_solve(rhs,adjoint=False):
        columns=1 if np.ndim(rhs)==1 else np.shape(rhs)[1]
        stage.pc_count('port_solves'); stage.pc_count('port_rhs_columns',columns)
        value=original_solve(rhs,adjoint=adjoint);last_port[0]=value
        ports.append(dict(adjoint=adjoint,shape=list(np.shape(rhs)),RHS_columns=columns))
        return value
    bar.solve_port=port_solve
    a=packet.a; weights=np.bincount(a['erows']//packet.lt,weights=np.abs(a['evals']),minlength=packet.nc)
    weights=weights*np.linalg.norm(a['S'],axis=(1,2))[a['classes']]
    cn=float(np.linalg.norm(C)); scale_certs={}
    def scale(x):
        norms=np.linalg.norm(packet._expand(x),axis=1); pn=float(np.linalg.norm(last_port[0]))
        value=float(weights@norms+cn*pn)
        scale_certs[array_hash(x)]=dict(input_array_sha256=array_hash(x),weights=weights.tolist(),
            expanded_cell_norms=norms.tolist(),C_norm=cn,closed_port_norm=pn,value=value)
        return value
    result.update(port_setup_seconds=setup_seconds,port_H_condition=bar.ports.cond_H,
        original_C_sha256=array_hash(C),Hhat_sha256=array_hash(bar.ports.H))
    joint_item=dict(rows=ids.tolist(),matrix=prior['matrix'],**prior['factor_inventory'])
    joint=SelectedBundle(joint_item,root/'v26',kind='joint',count=stage.pc_count,guard=stage.guard)
    try:
        reload=joint.witnesses((422601,422602),bar.apply,bar.adjoint,packet.nt)
        result['factor_reloads'].append(dict(block='J',source_sha=own['v26_source_sha'],
            rows_sha256=array_hash(ids),row_count=len(ids),**reload))
        write_json(stage.artifact/'reload_progress.json',result)
        if not reload['qualified']:
            return dict(result,status='JOINT_RELOAD_UNSAFE',decision='NUMERICALLY_UNRESOLVED')
        rhs=a['b'];barb=bar.reduced_rhs(rhs)
        for item in own['states']:
            stage.guard(); name=item['name']; p26=by26[name]; p32=by32[name]
            parent=io.checked_json(item['parent_result'],root/'v24')
            if (parent['source_sha']!=own['upstream_source_sha'] or parent['operator_packet']['sha256']!=own['action_sha256']
                    or parent['cycles'][3]['state']!=item['state']
                    or p26['input_state']!=item['state'] or p26['diagnostic_arrays']!=item['v26_arrays']
                    or p26['old_direction_arrays']!=item['v25_arrays']
                    or not p26['trustworthy'] or not p26['new_direction_resolved'] or p26['rank']!=9 or not all(p26['gates'].values())
                    or oldrows[name]['input_state']!=item['state'] or oldrows[name]['diagnostic_arrays']!=item['v25_arrays']
                    or p32['input_state']!=item['state'] or p32['diagnostic_arrays']!=item['v32_arrays']
                    or p32['v25_arrays']!=item['v25_arrays'] or p32['v26_arrays']!=item['v26_arrays']
                    or not p32['trustworthy'] or not all(p32['gates'].values())):
                raise ValueError('V33 named parent/state/cache qualification')
            values=io.physical_state(item,packet); t=values['trace'];closed=bar.close(t,rhs)
            full_r=rhs-packet.apply(values['z']);r=barb-bar.apply(t)
            identity=dict(exact_trace_port_z_concat=bool(np.array_equal(values['z'],np.r_[t,values['port']])),
                saved_trace_residual_full_b_relative=float(np.linalg.norm(r-values['residual'][:packet.nt])/packet.bnorm),
                saved_full_residual_full_b_relative=float(np.linalg.norm(full_r-values['residual'])/packet.bnorm),
                port_reclosure_operation_relative=float(np.linalg.norm(closed[packet.nt:]-values['port'])/(1+np.linalg.norm(values['port']))),
                port_residual_full_b_relative=float(np.linalg.norm(full_r[packet.nt:])/packet.bnorm),
                homogeneous_direction=True,internal_particular_added=False)
            if (not identity['exact_trace_port_z_concat'] or
                    max(identity[k] for k in ('saved_trace_residual_full_b_relative','saved_full_residual_full_b_relative'))>1e-11 or
                    max(identity[k] for k in ('port_reclosure_operation_relative','port_residual_full_b_relative'))>1e-10):
                raise ValueError('V33 actual state/port identity')
            olda=load_members(item['v25_arrays'],('directions','images'),root/'v25')
            cached=load_members(item['v26_arrays'],('joint_direction','joint_image'),root/'v26')
            reta=load_members(item['v32_arrays'],('return_direction','return_image'),root/'v32')
            support_inventory(olda['directions'],olda['images'],groups,packet.nt)
            qj=cached['joint_direction']; outside=(groups!=5)&(groups!=7)
            if qj.shape!=(packet.nt,) or np.count_nonzero(qj[outside]): raise ValueError('J cache support')
            flow,scales=direct_input(olda['directions'],olda['images'],qj,reta['return_direction'],ids,joint.solve,bar.apply,scale)
            flow.update(input_residual=r,qj=qj,aqj=cached['joint_image'],aqret_cached=reta['return_image'],
                joint_local_image=joint.A@flow['k'][ids],audited_full_residual=full_r,reclosed_port=closed[packet.nt:])
            metrics=certificates(flow,r,ids,bn=packet.bnorm,scales=scales)
            # Independent J solve quality retains the stricter original witness limits.
            je=float(np.linalg.norm(flow['joint_local_image']-flow['au'][ids]));jn=float(np.linalg.norm(flow['au'][ids]))
            jop=float(joint.A1*np.linalg.norm(flow['k'][ids])+jn)
            solve_check=dict(error_norm=je,rhs_norm=jn,operand_scale=jop,
                relative=je/jn if jn else (0. if je==0 else None),operation_relative=je/jop if jop else (0. if je==0 else None))
            if solve_check['relative'] is None or solve_check['relative']>1e-8 or solve_check['operation_relative'] is None or solve_check['operation_relative']>1e-12:
                metrics['trustworthy']=False
            receipt=atomic_arrays(stage.artifact/(name+'.npz'),**flow)
            row=dict(name=name,parent_result=item['parent_result'],input_state=item['state'],
                v25_arrays=item['v25_arrays'],v26_arrays=item['v26_arrays'],v32_arrays=item['v32_arrays'],
                identity=identity,joint_feedback_solve=solve_check,
                operator_action_sha256=own['action_sha256'],action_operation_scales=scales,
                scale_provenance=dict(method='cell_S_expand_plus_C_port_bound',action_sha256=own['action_sha256'],
                    operands={k:scale_certs[array_hash(flow[k])] for k in scales}),
                **metrics,diagnostic_arrays=receipt)
            result['rows'].append(row);write_json(stage.artifact/(name+'.json'),row)
            write_json(stage.artifact/'partial_result.json',result)
            stage.event('full_input_diagnosed',name=name,rho_full=row['rho_full'],rho0=row['rho0'],trustworthy=row['trustworthy'])
            if not row['trustworthy']:
                return dict(result,status='NUMERICALLY_UNRESOLVED',decision='NUMERICALLY_UNRESOLVED')
        result['factor_reloads'][0].update(solve_calls=joint.calls,RHS_columns=joint.RHS_columns,
            triangular_passes=2*joint.calls,solve_seconds=joint.seconds)
        result.update(status='DIAGNOSTIC_COMPLETE',decision=decision(result['rows']),
            joint_solve_calls=joint.calls,joint_RHS_columns=joint.RHS_columns,joint_solve_seconds=joint.seconds,
            port_seconds=bar.costs,port_rhs_inventory=ports,worker_wall_after_packet_load_seconds=perf_counter()-began,
            cost_timers_nested=True,neural_20percent_increment='NOT_DEMONSTRATED')
        return result
    finally:
        joint.close()
