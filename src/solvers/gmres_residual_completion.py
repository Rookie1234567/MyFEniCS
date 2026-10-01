"""V18 original-equation correction and separately resumed projected LSQR.

No reference is opened until all solve/selection states are frozen.  G never
loads Q/U/R; R imports the original V17 recurrence into independent V18 slots.
"""
import json
from pathlib import Path

import numpy as np

from src.runners.autonomous_neural_head import original_gate
from src.runners.task042_shared import write_json
from src.solvers.augmented_trace_lsqr import BarAction
from src.solvers.bounded_complex_lsqr import LSQRState
from src.solvers.gmres_cycle_commit import close_point,cycle_commit
from src.solvers.local_trace_study import ports_for,physical_qualification
from src.solvers.neural_fe_action_packet import array_hash,file_hash
from src.solvers.resumable_lsqr_checkpoint import RollingCheckpoint
from src.solvers import resumable_trace_study as previous


def load_state(stage,item,*,legacy=False):
    state=item['state'];path=Path(state['path']).resolve()
    allowed=stage.io.ROOT/'benchmarks/artifacts/task042'/('v17' if legacy else 'v18')
    if not path.is_relative_to(allowed) or file_hash(path)!=state['sha256']:raise ValueError('V18 frozen state ownership/hash differs')
    with np.load(path,allow_pickle=False) as f:arrays={k:np.array(f[k]) for k in f.files}
    for key in ('trace','port','z'):
        if key not in arrays or not np.isfinite(arrays[key]).all():raise ValueError('missing/nonfinite complete state')
    if arrays['trace'].shape!=(stage.packet.nt,) or arrays['port'].shape!=(40,) or arrays['z'].shape!=(stage.packet.nt+40,):
        raise ValueError('V18 trace/port/full inventory differs')
    if not np.array_equal(arrays['z'][:stage.packet.nt],arrays['trace']) or not np.array_equal(arrays['z'][stage.packet.nt:],arrays['port']):
        raise ValueError('V18 full state trace/port composition differs')
    if array_hash(arrays['z'])!=state['z_sha256']:raise ValueError('V18 z array hash differs')
    return arrays


def preflight(stage,*,state_loader=None):
    state_loader=state_loader or load_state
    bar=BarAction(ports_for(stage));rows={}
    for family in ('GPOLY','GNN'):
        try:
            item=stage.own_plan['initial_states'][family];arrays=state_loader(stage,item,legacy=True)
            closed,relative=close_point(bar,arrays['trace'],stage.packet.a['b'])
            port_difference=float(np.linalg.norm(closed['port']-arrays['port'])/max(np.linalg.norm(closed['port'])+np.linalg.norm(arrays['port']),1e-300))
            residual_difference=float(np.linalg.norm(closed['residual']-arrays['residual'])/stage.packet.bnorm)
            repeat=stage.packet.a['b']-stage.packet.apply(closed['z'])
            repeated=float(np.linalg.norm(repeat-closed['residual'])/stage.packet.bnorm)
            audit=stage.audit(closed['z']);gate=original_gate(audit)
            qualified=bool(relative<=1e-8 and residual_difference<=1e-8 and port_difference<=1e-12
                and audit['port_operation_relative']<=1e-12 and max(audit['recovery_relative'],audit['schur_original_identity_operation_relative'])<=1e-10
                and audit['slave_storage_max']==0)
            rows[family]=dict(qualified=qualified,audit=audit,original_equation_gate=gate,
                shape=dict(trace=stage.packet.nt,port=40,z=stage.packet.nt+40),initial_state=item,
                original_closed_identity_relative=relative,port_difference_operation_relative=port_difference,
                saved_vs_original_residual_full_b_relative=residual_difference,repeated_action_full_b_difference=repeated)
            stage.event('F0_original_closed_baseline',library=family,qualified=qualified,rho=gate['rho'])
        except (OSError,ValueError) as error:rows[family]=dict(qualified=False,error=str(error))
        write_json(stage.artifact/'preflight_partial.json',rows);stage.durable_counts()
    return dict(status='GMRES_PREFLIGHT_COMPLETE',libraries=rows,reference_read=False,hidden_training=False,
                new_image_or_GK_pair_tests=False,signature='original close full-z; all40 retained')


def passed(stage,row):
    if row['original_equation_gate']['status']!='ORIGINAL_EQUATION_PASS':return
    path=stage.io.ARTIFACT_ROOT/('FIRST_PASS_'+stage.family_name+'.json')
    if not path.exists():write_json(path,dict(row,algorithm=stage.algorithm_name,library=stage.family_name,first_pass_source=stage.source))


def gmres_route(stage):
    family=stage.family_name;algorithm=stage.algorithm_name;pre,_=stage.io.read_result('PREFLIGHT')
    if not pre['libraries'].get(family,{}).get('qualified'):return dict(status='NOT_RUN_LIBRARY_INTERFACE',queue_frozen=True)
    root=stage.io.ARTIFACT_ROOT;work=root/(algorithm+'_'+family);work.mkdir(exist_ok=True)
    if algorithm=='G64':source=dict(stage.own_plan['initial_states'][family],original_equation_gate=pre['libraries'][family]['original_equation_gate'])
    else:
        path=root/('G64_'+family)/'last_cycle.json'
        if not path.exists():return dict(status='NOT_RUN_G64_NO_COMMITTED_CYCLE',queue_frozen=True)
        source=json.loads(path.read_text())
    original=load_state(stage,source,legacy=algorithm=='G64');t=original['trace']
    bar=BarAction(ports_for(stage));rhs=stage.packet.a['b'];target=stage.specification.derived['target_cycles']
    maximum=16 if algorithm=='G64' else 8;polish=2 if algorithm=='G64' else 1
    history_path=work/'cycles.jsonl';history=[]
    for p in sorted((work/'cycles').glob('CYCLE_*/commit.json')) if (work/'cycles').exists() else ():
        row=json.loads(p.read_text());load_state(stage,row)
        if not row['committed'] or row['audit_pending']:raise ValueError('invalid committed GMRES cycle')
        history.append(row)
    history.sort(key=lambda r:r['cycle'])
    if any(row['cycle']!=j+1 for j,row in enumerate(history)):raise ValueError('noncontiguous GMRES cycle boundaries')
    if history:t=load_state(stage,history[-1])['trace']
    original_rho=source['original_equation_gate']['rho'];initial_gate=source['original_equation_gate']
    first_pass=next((r['cycle'] for r in history if r['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS'),None)
    status='GMRES_CYCLE_LIMIT';final=history[-1] if history else source;budget=json.loads(stage.window.BUDGET_PATH.read_text())
    while len(history)<maximum:
        cycle=len(history)+1
        if first_pass is not None:
            if final['original_equation_gate']['rho']<=1e-8 or cycle>first_pass+polish:status='ORIGINAL_EQUATION_PASS';break
        elif cycle>target:break
        basic=8 if algorithm=='G64' else 4
        if cycle>basic and first_pass is None and 1-history[basic-1]['original_equation_gate']['rho']/original_rho<.1:
            status='GMRES_NO_EXTENSION_PROGRESS';break
        prior=stage.base['routes'][family];elapsed=__import__('time').monotonic()-stage.run_started
        if prior['G_wall_seconds']+elapsed>budget['GMRES_total_ceiling_seconds']-60 or prior['wall_seconds']+elapsed>budget['uniform_route_wall_seconds']-60:
            status='GMRES_WALL_BOUNDARY';break
        cycle_directory=work/'cycles'/('CYCLE_'+str(cycle).zfill(4))
        returned_boundary=any((cycle_directory/'numeric').glob('slot*.commit.json'))
        cap=1024 if algorithm=='G64' else 2048
        needed=0 if returned_boundary else stage.restart
        if prior['arnoldi_upper'][algorithm]+stage.arnoldi_run+needed>cap:
            status='GMRES_ARNOLDI_BUDGET_STOP';break
        stage.guard(extra_actions=needed+16);stage.gmres_pending=not returned_boundary;stage.durable_counts()
        metadata=dict(cycle=cycle,algorithm=algorithm,library=family,source_sha=stage.source,
            input_sha256=stage.specification.input_sha256,start_rho=original_rho,parent_state=final['state'],reference_arrays_read=False)
        contract=dict(action_sha256=stage.own_plan['action_sha256'],physical_sha256=stage.own_plan['physical_sha256'],
            master_sha256=array_hash(stage.packet.a['masters']),window_sha256=file_hash(stage.window.WINDOW_PATH),algorithm_route=algorithm,library=family)
        row=cycle_commit(bar,t,rhs,cycle_directory,contract,metadata,stage.audit,
            restart=stage.restart,returned=stage.gmres_returned,io_begin=stage.begin_numeric_io,io_done=stage.complete_numeric_io)
        stage.gmres_pending=False;stage.durable_counts(reserve=0)
        history.append(row);final=row;t=load_state(stage,row)['trace']
        write_json(work/'last_cycle.json',row)
        with history_path.open('a') as f:f.write(json.dumps(row)+'\n');f.flush()
        passed(stage,row)
        if row['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS' and first_pass is None:first_pass=cycle
        stage.event('GMRES_cycle_complete',algorithm=algorithm,library=family,cycle=cycle,inner_iterations=row['inner']['inner_iterations'],info=row['inner']['info'],rho=row['original_equation_gate']['rho'],boundary_resumed=row['returned_boundary_resumed'])
        tolerance=max(1e-10,100*pre['libraries'][family]['repeated_action_full_b_difference'])
        if len(history)>=3 and all(history[-3+j+1]['audit']['schur_relative']>history[-3+j]['audit']['schur_relative']+tolerance for j in range(2)):
            repeated=stage.audit(load_state(stage,final)['z'])
            write_json(work/'two_increases_recheck.json',dict(audit=repeated,original=row['audit'],threshold=tolerance))
            status='GMRES_TWO_CYCLE_INCREASE';break
    if final['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS':status='ORIGINAL_EQUATION_PASS'
    return dict(status=status,route=algorithm+'-AFTER-'+family,final=final,cycles=history,
        start=source,start_rho=original_rho,first_pass_cycle=first_pass,Q_U_R_loaded=False,
        bar_action_costs_inclusive_seconds=bar.costs.copy(),nested_timers_additive=False,
        reference_read=False,queue_frozen=True,hidden_training=False)


def load_R_production(stage,op):
    family=stage.family_name;store=RollingCheckpoint(stage.io.ARTIFACT_ROOT/family/'rolling',previous.identity(stage,family,op))
    if any(store.directory.glob('*.commit.json')):
        manifest,arrays,errors=store.read();state=LSQRState.restore({k[3:]:v for k,v in arrays.items() if k.startswith('GK_')})
        return store,state,arrays.get('base_trace'),manifest['metadata']['mode'],manifest,errors
    item=stage.own_plan['initial_recursions'][family];initial=stage.own_plan['initial_states'][family]
    arrays=load_state(stage,initial,legacy=True);base=None;errors=[]
    try:
        directory=Path(item['directory']).resolve()
        if not directory.is_relative_to(stage.io.ROOT/'benchmarks/artifacts/task042/v17'):raise ValueError('old GK ownership differs')
        manifest,gk,errors=RollingCheckpoint(directory,item['identity']).read()
        if manifest['generation']!=item['generation'] or manifest['arrays_sha256']!=item['arrays_sha256']:raise ValueError('old GK generation/hash differs')
        state=LSQRState.restore({k[3:]:v for k,v in gk.items() if k.startswith('GK_')})
        if state.values['iteration']!=initial['logical_iteration'] or not np.array_equal(state.values['x'],arrays['y']):raise ValueError('V17 GK/full state mismatch')
        mode=dict(mode='CONTINUOUS_V17_GK',epoch=0,legacy_persisted_iteration=initial['logical_iteration'],legacy_observed_iteration=initial['logical_iteration'],V17_mode=initial['mode'])
    except (OSError,ValueError,KeyError) as error:
        base=arrays['trace'];f=op.pr(op.bar.reduced_rhs(stage.packet.a['b'])-op.bar.apply(base));state=LSQRState.initialize(op.adjoint,f)
        mode=dict(mode='RESIDUAL_CORRECTION_RESTART',epoch=1,base_logical_iteration=initial['logical_iteration'],legacy_persisted_iteration=initial['logical_iteration'],legacy_observed_iteration=initial['logical_iteration'],reason=str(error))
        stage.base['routes'][family]['correction_restarts']=1
        stage.window.journal('V18_missing_or_bad_GK_correction_epoch',library=family,mode=mode)
    return store,state,base,mode,None,errors


def continue_route(stage):
    stage.production_loader=lambda op:load_R_production(stage,op)
    result=previous.continue_route(stage)
    if 'final' in result:passed(stage,result['final'])
    result['initial_chain']='original V17 GK only; no GMRES trace or reference initialization'
    return result


def verify(stage,*,state_loader=None):
    state_loader=state_loader or load_state
    from src.io.neural_fe_continuation import read_index,V7_ROOT
    from src.runners.autonomous_neural_head import owned
    from src.solvers.neural_fe_blind_reference import independent_physics
    from src.runners.task042_experiment import thread_qualification
    root=stage.io.ARTIFACT_ROOT
    if not (root/'FROZEN.json').exists():raise ValueError('V18 queue must freeze before reference')
    freeze=json.loads((root/'FROZEN.json').read_text());items=freeze['validation_inventory'];candidates={};sources={};seen=set();missing=[]
    for item in items:
        try:arrays=state_loader(stage,item,legacy=item.get('legacy',False))
        except (OSError,ValueError) as error:missing.append(dict(name=item['name'],error=str(error)));continue
        sha=array_hash(arrays['z'])
        if sha in seen:continue
        seen.add(sha);candidates[item['name']]=arrays['z'];sources[item['name']]=item
    if not 1<=len(candidates)<=12:raise ValueError('V18 frozen field inventory exceeds limit')
    stage.event('all_solver_states_frozen_before_REF7',states=list(candidates))
    ref,_=read_index('blind_reference');path=owned(ref['reference_state'],V7_ROOT)
    if file_hash(path)!=stage.own_plan['reference_sha256']:raise ValueError('REF7 hash differs')
    with np.load(path,allow_pickle=False) as f:reference=np.array(f['z'])
    stage.meta['reference_arrays_read']=True;stage.count('field_states',len(candidates));stage.count('original_audits',len(candidates)+1)
    physics,comparisons=independent_physics(stage.design,stage.packet,reference,candidates,stage.artifact)
    rows={name:physical_qualification(physics['rows'][name],comparisons[name],physics['reference_native_pass']) for name in candidates}
    return dict(status='FROZEN_VALIDATION_COMPLETE',rows=rows,states_read=len(candidates),missing=missing,state_sources=sources,
        reference_identity=ref['reference_state'],reference_audit=physics['rows']['REFERENCE']['audit'],reference_native_pass=physics['reference_native_pass'],
        reference_feedback_to_solver=False,no_new_solve=True,no_new_LU=True,threads=thread_qualification(),queue_frozen=True)
