"""Two fixed cold residuals, seven readonly bundles, one return direction."""
from pathlib import Path
from time import perf_counter
import numpy as np
from src.io import return_block_diagnostic as io
from src.solvers.return_block_direction import (SelectedBundle,OUTER_BLOCKS,NAMES,
    return_direction,extend_nine,decision)
from src.solvers.joint_block_direction import selected_rows,pair
from src.solvers.joint_block_study import cached_directions
from src.solvers.local_block_study import mapping
from src.solvers.local_block_readiness import local_readiness
from src.solvers.fixed_p3_ilu0 import direct_C
from src.solvers.stable_head_varpro import PortBlocks
from src.solvers.augmented_trace_lsqr import BarAction
from src.solvers.neural_fe_action_packet import array_hash,file_hash
from src.runners.orthonormal_trace_reprofile import atomic_arrays
from src.runners.task042_shared import write_json


def process_rss():
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith('VmRSS:'):return int(line.split()[1])*1024
    return None


def prior_arrays(item,nt):
    path=Path(item['path']).resolve()
    if not path.is_relative_to(io.ROOT/'benchmarks/artifacts/task042/v26') or file_hash(path)!=item['sha256']:
        raise ValueError('V26 cached container path/hash')
    keys=('joint_direction','joint_image','coefficients','diagnostic_residual')
    with np.load(path,allow_pickle=False) as f:arrays={k:np.array(f[k]) for k in keys}
    for k,v in arrays.items():
        if array_hash(v)!=item[k+'_sha256'] or not np.isfinite(v).all() or v.shape!=((9,) if k=='coefficients' else (nt,)):
            raise ValueError('V26 nine baseline member/hash/shape')
    return arrays


def run(stage):
    io=stage.io
    began=perf_counter();packet=stage.packet;own=stage.own_plan
    if (packet.nt,packet.np,packet.size)!=(18144,40,18184):raise ValueError('V27 complete original row inventory')
    if array_hash(packet.a['masters'])!=own['canonical_master_sha256'] or array_hash(packet.a['b'])!=own['b_sha256']:
        raise ValueError('V27 master/RHS identity')
    setup=io.checked_json(own['local_setup'],io.ROOT/'benchmarks/artifacts/task042/v24')
    ready=local_readiness(setup,expected_map=own['map'])
    if (not ready['qualified'] or setup['source_sha']!=own['upstream_source_sha']
            or setup['operator_packet']['sha256']!=own['action_sha256']):raise ValueError('V24 ready seal/source/operator')
    groups,mapcheck=mapping(stage);ids=selected_rows(groups)
    if array_hash(ids)!=own['joint_rows_sha256']:raise ValueError('fixed J canonical order')
    prior=io.checked_json(own['v26_result'],io.ROOT/'benchmarks/artifacts/task042/v26')
    old=io.checked_json(own['v25_result'],io.ROOT/'benchmarks/artifacts/task042/v25')
    from benchmarks.collect_task042_block_direction import fixed_inventory
    oldrows={x['name']:x for x in fixed_inventory(old)}
    if (prior['source_sha']!=own['v26_source_sha'] or old['source_sha']!=own['v25_source_sha']
            or prior['operator_packet']['sha256']!=own['action_sha256']
            or len(prior['rows'])!=2 or {x['name'] for x in prior['rows']}!=set(NAMES)):
        raise ValueError('nine/eight source or sample inventory')
    prow={x['name']:x for x in prior['rows']}
    if not all(x['trustworthy'] and x['new_direction_resolved'] and x['rank']==9 and all(x['gates'].values()) for x in prow.values()):
        raise ValueError('V26 baseline qualification')
    if not prior['factor_safety']['qualified'] or prior['factor_safety']['rcond1_estimate']<1e-12:
        raise ValueError('V26 original joint factor safety')
    one=3888**2*16;largest=2913**2*16
    planned=3*2**30+4*one+4*largest+packet.nt*(40*4+10*10)*16
    capacity=dict(simultaneous_planned_bytes=planned,qualified=planned<=8*2**30,derived_not_RSS=True,
        J_matrix_and_LU_bytes=2*one,max_outer_matrix_and_LU_bytes=2*largest,
        max_outer_single_LU_bytes=largest,full_hash_copy=False,one_outer_bundle_at_a_time=True,
        packet_libraries_workspace_allowance_bytes=3*2**30,no_new_factor_bytes=True)
    write_json(stage.artifact/'capacity_before_reads.json',capacity)
    if not capacity['qualified']:raise MemoryError('V27 simultaneous planning Gate')
    stage.meta.update(simultaneous_planned_bytes=planned,factor_status='READONLY_JOINT_AND_OUTER6_DENSE_LU_PRESENT',
        new_local_assemblies=0,new_local_factors=0,new_gecon=0,old_eight_LU_loaded=False,
        selected_old_outer_LU_blocks=list(OUTER_BLOCKS),old5_7_LU_read=False,
        rank_upper_bound=3888,full_trace_rows=18144,full_space_preconditioner=False)
    result=dict(status='PENDING',rows=[],factor_readiness=ready,map_check=mapcheck,capacity=capacity,
        operator_identity={k:own[k] for k in ('action_sha256','physical_sha256','mode_sha256','canonical_master_sha256','b_sha256')},
        factor_reloads=[],source_lineage=dict(V24=own['upstream_source_sha'],V25=own['v25_source_sha'],V26=own['v26_source_sha']),
        new_solver_states=0,new_local_assemblies=0,new_local_factors=0,old5_7_LU_read=False,
        cache_reused_qj_vj=True,rank_upper_bound=3888,full_space_PC=False,decision='PENDING')
    stage.partial_result=result
    C=np.column_stack([direct_C(packet,np.eye(40,dtype=complex)[:,j]) for j in range(40)])
    started=perf_counter();bar=BarAction(PortBlocks(packet,np.vstack((C,packet.a['Hhat']))))
    stage.pc_count('port_factors');port_setup_seconds=perf_counter()-started
    original_solve=bar.solve_port;last_port=[np.zeros(40,complex)];port_inventory=[]
    def port_solve(rhs,adjoint=False):
        columns=1 if np.ndim(rhs)==1 else np.shape(rhs)[1]
        stage.pc_count('port_solves');stage.pc_count('port_rhs_columns',columns)
        value=original_solve(rhs,adjoint=adjoint);last_port[0]=value
        port_inventory.append(dict(adjoint=adjoint,shape=list(np.shape(rhs)),RHS_columns=columns))
        return value
    bar.solve_port=port_solve
    result.update(port_H_condition=bar.ports.cond_H,port_setup_seconds=port_setup_seconds,
        original_C_sha256=array_hash(C),Hhat_sha256=array_hash(bar.ports.H))
    a=packet.a;e_bound=np.bincount(a['erows']//packet.lt,weights=np.abs(a['evals']),minlength=packet.nc)
    s_norm=np.linalg.norm(a['S'],axis=(1,2))[a['classes']];Cnorm=float(np.linalg.norm(C))
    scale_certificates={}
    def scale(x):
        # Persist already-computed norm operands, without another original action
        # or expansion. Cached checker can recompute the reported bound.
        weights=e_bound*s_norm;expanded_norms=np.linalg.norm(packet._expand(x),axis=1)
        portnorm=float(np.linalg.norm(last_port[0]));value=float(np.dot(weights,expanded_norms)+Cnorm*portnorm)
        scale_certificates[array_hash(x)]=dict(input_array_sha256=array_hash(x),weights=weights.tolist(),
            expanded_cell_norms=expanded_norms.tolist(),C_norm=Cnorm,closed_port_norm=portnorm,value=value)
        return value
    joint_item=dict(rows=ids.tolist(),matrix=prior['matrix'],**prior['factor_inventory'])
    joint=SelectedBundle(joint_item,io.ROOT/'benchmarks/artifacts/task042/v26',kind='joint',count=stage.pc_count,guard=stage.guard)
    try:
        reload=joint.witnesses((422601,422602),bar.apply,bar.adjoint,packet.nt)
        result['factor_reloads'].append(dict(block='J',source_sha=own['v26_source_sha'],
            rows_sha256=array_hash(ids),row_count=len(ids),**reload))
        write_json(stage.artifact/'reload_progress.json',result)
        if not reload['qualified']:return dict(result,status='JOINT_RELOAD_UNSAFE',decision='NUMERICALLY_UNRESOLVED',dependent_samples='NOT_RUN')
        rhs=a['b'];barb=bar.reduced_rhs(rhs);samples=[]
        for item in own['states']:
            parent=io.checked_json(item['parent_result'],io.ROOT/'benchmarks/artifacts/task042/v24')
            if parent['source_sha']!=own['upstream_source_sha'] or parent['operator_packet']['sha256']!=own['action_sha256']:
                raise ValueError('named V24 parent source/operator')
            stage.guard();name=item['name'];previous=prow[name];v25=oldrows[name]
            if (previous['input_state']!=item['state'] or previous['diagnostic_arrays']!=item['v26_arrays']
                    or previous['old_direction_arrays']!=item['v25_arrays'] or v25['input_state']!=item['state']):
                raise ValueError('V27 named parent/state/cache binding')
            values=io.physical_state(item,packet);t=values['trace'];closed=bar.close(t,rhs)
            full_r=rhs-packet.apply(values['z']);r=barb-bar.apply(t)
            identity=dict(exact_trace_port_z_concat=bool(np.array_equal(values['z'][:packet.nt],t) and np.array_equal(values['z'][packet.nt:],values['port'])),
                saved_trace_residual_full_b_relative=float(np.linalg.norm(r-values['residual'][:packet.nt])/packet.bnorm),
                saved_full_residual_full_b_relative=float(np.linalg.norm(full_r-values['residual'])/packet.bnorm),
                port_reclosure_operation_relative=float(np.linalg.norm(closed[packet.nt:]-values['port'])/(1+np.linalg.norm(values['port']))),
                port_residual_full_b_relative=float(np.linalg.norm(full_r[packet.nt:])/packet.bnorm),
                homogeneous_direction=True,internal_particular_added=False)
            if not identity['exact_trace_port_z_concat'] or max(identity[k] for k in ('saved_trace_residual_full_b_relative','saved_full_residual_full_b_relative'))>1e-11 or max(identity[k] for k in ('port_reclosure_operation_relative','port_residual_full_b_relative'))>1e-10:
                raise ValueError('V27 original state/port identity')
            data=cached_directions(item['v25_arrays'],packet.nt);cached=prior_arrays(item['v26_arrays'],packet.nt)
            qj,vj=cached['joint_direction'],cached['joint_image'];cached_joint_image=bar.apply(qj)
            check=pair(cached_joint_image,vj);qj_scale=scale(qj)
            cached_joint_inner_image=joint.A@qj[ids];local_pair=pair(cached_joint_inner_image,r[ids])
            if np.count_nonzero(qj[(groups!=5)&(groups!=7)]) or check['operation_relative']>1e-10 or local_pair['operation_relative']>1e-10:
                raise ValueError('cached J direction or original response')
            Q9=np.column_stack((data['directions'],qj));W9=np.column_stack((data['images'],vj))
            c9=cached['coefficients'];e9=cached['diagnostic_residual']
            if np.linalg.norm(r-W9@c9-e9)/packet.bnorm>1e-11:raise ValueError('cached actual e9 differs from nine response')
            samples.append(dict(name=name,item=item,r=r,qj=qj,vj=vj,Q9=Q9,W9=W9,c9=c9,e9=e9,
                old_scales=np.r_[v25['operation_scales'],qj_scale],w=np.zeros(packet.nt,complex),
                identity=identity,cache_original_pair=check,cached_joint_inner_pair=local_pair,
                audited_full_residual=full_r,reclosed_port=closed[packet.nt:],qj_scale_certificate=scale_certificates[array_hash(qj)],
                cached_joint_image=cached_joint_image,cached_joint_inner_image=cached_joint_inner_image))
        # Bundle outer loop is intentional: exactly one load per block, two
        # actual RHS vectors plus two reload witnesses before releasing it.
        for b in OUTER_BLOCKS:
            stage.guard();before=process_rss();item=setup['block_inventory'][b]
            if item['block']!=b or item['rows']!=np.flatnonzero(groups==b).tolist():raise ValueError('outer canonical rows/source seal')
            bundle=SelectedBundle(item,io.ROOT/'benchmarks/artifacts/task042/v24/blocks',kind='outer',count=stage.pc_count,guard=stage.guard)
            try:
                reload=bundle.witnesses((422401+2*b,422402+2*b),bar.apply,n=packet.nt)
                if not reload['qualified']:raise ValueError('outer readonly solve/action unsafe')
                for sample in samples:sample['w'][bundle.rows]=bundle.solve(sample['vj'][bundle.rows])
                reload.update(block=b,source_sha=own['upstream_source_sha'],rows_sha256=array_hash(bundle.rows),
                    row_count=len(bundle.rows),triangular_passes=2*bundle.calls,solve_calls=bundle.calls,RHS_columns=bundle.RHS_columns,
                    solve_seconds=bundle.seconds,process_RSS_before_load=before,process_RSS_before_close=process_rss())
                result['factor_reloads'].append(reload)
            finally:bundle.close()
            reload['process_RSS_after_close']=process_rss();reload['page_reclamation']='process snapshot only; system file cache not claimed reclaimed'
            write_json(stage.artifact/'reload_progress.json',result)
            stage.event('outer_bundle_done',block=b,cumulative_readers=stage.counts['factor_readers'])
        for sample in samples:
            stage.guard();w=sample['w'];flow=return_direction(sample['qj'],w,joint.solve,ids,bar.apply,scale)
            # Conservatively use the pre-cancellation action operand scale.
            scales=flow['action_operation_scales']
            new_scale=max(scales['d'],scales['w']+scales['feedback'])
            cancel=float(np.linalg.norm(flow['image'][ids]));cancel_scale=scales['w']+scales['feedback']
            cancellation=dict(error_norm=cancel,operation_scale=cancel_scale,operation_relative=relative(cancel,cancel_scale),
                original_rhs_inner_pair=pair(flow['return_image'][ids],sample['r'][ids]),
                d_linearity=pair(flow['image'],flow['feedback_image']-flow['aw']),
                return_linearity=pair(flow['return_image'],sample['vj']+flow['image']),
                pre_cancel_Aw_inner_norm=float(np.linalg.norm(flow['aw'][ids])),
                pre_cancel_feedback_inner_norm=float(np.linalg.norm(flow['feedback_image'][ids])))
            if cancellation['operation_relative']>1e-10 or any(cancellation[k]['operation_relative']>1e-10 for k in ('original_rhs_inner_pair','d_linearity','return_linearity')):
                raise ValueError('true return cancellation/linearity Gate')
            metrics,arrays=extend_nine(sample['r'],sample['Q9'],sample['W9'],sample['c9'],sample['e9'],
                flow['direction'],flow['image'],bar.apply,bnorm=packet.bnorm,old_scales=sample['old_scales'],
                new_scale=new_scale,count=stage.pc_count)
            previous=prow[sample['name']]
            if abs(metrics['eta9']-previous['eta9'])>1e-10:raise ValueError('V26 eta9 baseline drift')
            support=np.zeros(packet.nt,bool);support[ids]=True
            regions={label:dict(qj_response_norm=float(np.linalg.norm(sample['vj'][mask])),d_response_norm=float(np.linalg.norm(flow['image'][mask])),
                return_response_norm=float(np.linalg.norm(flow['return_image'][mask])),old_e9_norm=float(np.linalg.norm(arrays['old_e9'][mask])),
                new_e10_norm=float(np.linalg.norm(arrays['diagnostic_residual'][mask]))) for label,mask in [('inside_J',support),('outside_J',~support)]}
            receipt=atomic_arrays(stage.artifact/(sample['name']+'.npz'),**arrays,
                w=w,aw=flow['aw'],feedback=flow['feedback'],feedback_image=flow['feedback_image'],
                return_direction=flow['return_direction'],return_image=flow['return_image'],
                audited_full_residual=sample['audited_full_residual'],reclosed_port=sample['reclosed_port'],
                cached_joint_image=sample['cached_joint_image'],cached_joint_inner_image=sample['cached_joint_inner_image'])
            row=dict(name=sample['name'],parent_result=sample['item']['parent_result'],input_state=sample['item']['state'],v25_arrays=sample['item']['v25_arrays'],v26_arrays=sample['item']['v26_arrays'],
                old_operation_scales=sample['old_scales'].tolist(),
                identity=sample['identity'],cached_original_pair=sample['cache_original_pair'],cached_joint_inner_pair=sample['cached_joint_inner_pair'],
                cancellation=cancellation,action_operation_scales=scales,operator_action_sha256=own['action_sha256'],
                scale_provenance=dict(method='cell_S_expand_plus_C_port_bound',action_sha256=own['action_sha256'],
                    scales=scales,old_scales=sample['old_scales'].tolist(),qj=sample['qj_scale_certificate'],
                    operands={key:scale_certificates[array_hash(flow[member])] for key,member in
                        [('w','w'),('d','direction'),('feedback','feedback'),('qret','return_direction')]}),
                regions=regions,**metrics,diagnostic_arrays=receipt)
            result['rows'].append(row);write_json(stage.artifact/(sample['name']+'.json'),row)
            stage.event('return_direction_diagnosed',name=row['name'],eta9=row['eta9'],eta10=row['eta10'],g10=row['g10'])
        result['factor_reloads'][0].update(solve_calls=joint.calls,RHS_columns=joint.RHS_columns,triangular_passes=2*joint.calls)
        result.update(status='DIAGNOSTIC_COMPLETE' if all(x['trustworthy'] for x in result['rows']) else 'NUMERICALLY_UNRESOLVED',
            decision=decision(result['rows']),joint_solve_calls=joint.calls,joint_RHS_columns=joint.RHS_columns,joint_solve_seconds=joint.seconds,
            port_seconds=bar.costs,port_rhs_inventory=port_inventory,worker_wall_after_packet_load_seconds=perf_counter()-began,
            cost_timers_nested=True,neural_20percent_increment='NOT_DEMONSTRATED')
        return result
    finally:joint.close()
