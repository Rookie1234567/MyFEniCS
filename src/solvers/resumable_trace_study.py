"""V17 serial paired campaign using the frozen V16 projected operator."""
import gc
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from src.io.resumable_trace_campaign import ARTIFACT_ROOT
from src.runners.autonomous_neural_head import original_gate
from src.runners.orthonormal_trace_reprofile import atomic_arrays
from src.runners.task042_shared import write_json
from src.solvers.augmented_trace_lsqr import BarAction,operation_pair,projected_checks
from src.solvers.augmented_trace_study import load_image,algebra_witness
from src.solvers.bounded_complex_lsqr import LSQRState
from src.solvers.local_trace_study import ports_for,physical_qualification
from src.solvers.neural_fe_action_packet import array_hash,file_hash
from src.solvers.resumable_lsqr_checkpoint import RollingCheckpoint
from src.solvers.resumable_trace_gmres import correction_cycle
from src.solvers.resumable_trace_window import ledger,snapshot,journal


def legacy_arrays(stage,family):
    item=stage.own_plan['legacy'][family];state=item['state'];p=Path(state['path']).resolve()
    if not p.is_relative_to(stage.io.ROOT/'benchmarks/artifacts/task042/v16') or file_hash(p)!=state['sha256']:
        raise ValueError('frozen legacy checkpoint missing/hash differs')
    with np.load(p,allow_pickle=False) as stream:arrays={k:np.array(stream[k]) for k in stream.files}
    if arrays['z'].shape!=(stage.packet.size,) or array_hash(arrays['z'])!=state['z_sha256']:
        raise ValueError('legacy z inventory differs')
    return arrays,item


def identity(stage,family,op):
    image=stage.own_plan['images'][family]
    return dict(algorithm=LSQRState.version,dtype='complex128',family=family,
        action_sha256=stage.own_plan['action_sha256'],physical_sha256=stage.own_plan['physical_sha256'],
        master_sha256=array_hash(stage.packet.a['masters']),rhs_sha256=array_hash(stage.packet.a['b']),
        Q=image['basis_identity'],U_sha256=image['U']['sha256'],R_sha256=image['R']['sha256'],
        window_sha256=file_hash(stage.window.WINDOW_PATH))


def migrate(stage,family,op):
    arrays,item=legacy_arrays(stage,family);f=op.rhs(stage.packet.a['b'])
    if family=='GNN':
        if item['persisted_iteration']!=0:raise ValueError('GNN only recorded zero initializer authorized')
        state=LSQRState.initialize(op.adjoint,f);mode='INITIALIZE_ORIGINAL_F'
    else:
        keys=('iteration','x','u','v','w','alpha','beta','phibar','rhobar')
        if any('GK_'+k not in arrays for k in keys):
            # Explicit correction epoch from the trusted saved full trace only.
            return None,arrays['trace'],dict(mode='RESIDUAL_CORRECTION_RESTART',epoch=1,
                legacy_persisted_iteration=item['persisted_iteration'],legacy_observed_iteration=item['observed_iteration'])
        values={k:arrays['GK_'+k] for k in keys}
        values.update(rhs_norm=float(np.linalg.norm(f)),terminated=bool(float(values['alpha'])==0 or float(values['beta'])==0))
        state=LSQRState.restore(values)
        if state.values['iteration']!=256 or not np.array_equal(state.values['x'],arrays['y']):
            raise ValueError('legacy GK iteration/x do not match persisted y')
        mode='CONTINUOUS_LEGACY_GK'
    return state,None,dict(mode=mode,epoch=0,legacy_persisted_iteration=item['persisted_iteration'],
                            legacy_observed_iteration=item['observed_iteration'])


def qualify_pair(stage,family,op):
    migrated,base,mode=migrate(stage,family,op)
    if migrated is None:
        f=op.pr(op.bar.reduced_rhs(stage.packet.a['b'])-op.bar.apply(base));migrated=LSQRState.initialize(op.adjoint,f)
    original=migrated.export();full=LSQRState.restore(original);part=LSQRState.restore(original)
    for _ in range(32):full.step(op.apply,op.adjoint)
    for _ in range(16):part.step(op.apply,op.adjoint)
    store=RollingCheckpoint(stage.artifact/('SHORT_'+family),identity(stage,family,op))
    store.save({'GK_'+k:np.asarray(v) for k,v in part.export().items()},dict(test_only=True,source_sha=stage.source))
    # Independent process reads exactly the committed NPZ/schema/hashes. It
    # does not rebuild a runtime or receive any accurate solution.
    req=stage.artifact/('reader_'+family+'.json');write_json(req,store.identity)
    output=stage.artifact/('reader_'+family+'.npz')
    code="from pathlib import Path;import json,numpy as np,sys;from src.solvers.resumable_lsqr_checkpoint import RollingCheckpoint;m,a,e=RollingCheckpoint(sys.argv[1],json.loads(Path(sys.argv[2]).read_text())).read();np.savez(sys.argv[3],**a)"
    subprocess.run([sys.executable,'-c',code,str(store.directory),str(req),str(output)],check=True)
    with np.load(output,allow_pickle=False) as stream:part=LSQRState.restore({k[3:]:stream[k] for k in stream.files})
    for _ in range(16):part.step(op.apply,op.adjoint)
    differences={k:operation_pair(np.asarray(v),np.asarray(part.values[k])) for k,v in full.export().items() if k!='terminated'}
    same=all(v['operation_relative']<=1e-12 for v in differences.values()) and full.values['terminated']==part.values['terminated']
    fullpoint=op.restore(full.values['x'],stage.packet.a['b']);partpoint=op.restore(part.values['x'],stage.packet.a['b'])
    zpair=operation_pair(fullpoint['z'],partpoint['z']);rpair=operation_pair(stage.packet.apply(fullpoint['z']),stage.packet.apply(partpoint['z']))
    return dict(qualified=bool(same and zpair['operation_relative']<=1e-12 and rpair['operation_relative']<=1e-12),
        mode=mode,full_GK_differences=differences,z=zpair,original_action=rpair,
        independent_reader=True,short_steps=32,production_progress_unchanged=True,reference_read=False)


def preflight(stage):
    rows={}
    for family in ('GPOLY','GNN'):
        stage.event('R1_library_begin',library=family)
        try:
            op,loading=load_image(stage,stage.own_plan['images'][family])
            checks=projected_checks(op,stage.packet.a['b'])
            # Persist lost GNN interface scalars BEFORE the short recurrence.
            write_json(stage.artifact/(family+'_operator_checks.json'),checks)
            original_artifact=stage.artifact;stage.artifact=original_artifact/family;stage.artifact.mkdir()
            try:witness=algebra_witness(stage,op)
            finally:stage.artifact=original_artifact
            pair=qualify_pair(stage,family,op)
            rows[family]=dict(qualified=bool(checks['qualified'] and witness['qualified'] and pair['qualified']),
                             operator_checks=checks,algebra_witness=witness,resume_pair=pair,loading_seconds=loading,
                             image_rebuilt=False,original_image=stage.own_plan['images'][family])
            del op;gc.collect();stage.durable_counts()
        except (FileNotFoundError,ValueError) as error:
            rows[family]=dict(qualified=False,error=str(error));gc.collect()
        write_json(stage.artifact/'qualification_partial.json',rows)
    return dict(status='RESUME_QUALIFICATION_COMPLETE',libraries=rows,queue_frozen=True,reference_read=False)


def load_production(stage,family,op):
    store=RollingCheckpoint(ARTIFACT_ROOT/family/'rolling',identity(stage,family,op))
    if any(store.directory.glob('*.commit.json')):
        manifest,arrays,errors=store.read();mode=manifest['metadata']['mode'];base=arrays.get('base_trace')
        state=LSQRState.restore({k[3:]:v for k,v in arrays.items() if k.startswith('GK_')})
        return store,state,base,mode,manifest,errors
    state,base,mode=migrate(stage,family,op)
    if state is None:
        stage.base['routes'][family]['correction_restarts']+=1
        f=op.pr(op.bar.reduced_rhs(stage.packet.a['b'])-op.bar.apply(base));state=LSQRState.initialize(op.adjoint,f)
    return store,state,base,mode,None,[]


def physical_point(op,state,rhs,base=None):
    point=op.restore(state.values['x'],rhs if base is None else np.r_[op.bar.reduced_rhs(rhs)-op.bar.apply(base),np.zeros(40,complex)])
    if base is not None:
        # Correction rhs above is the already port-closed trace equation, so
        # recompute the complete port using the original unchanged physical b.
        point['trace']+=base
        point['port']=op.bar.close(point['trace'],rhs)
        point['z']=np.r_[point['trace'],point['port']]
    return point


def save_gk(stage,store,state,base,mode,last_audit=None):
    stage.durable_counts()
    arrays={'GK_'+k:np.asarray(v) for k,v in state.export().items()}
    if base is not None:arrays['base_trace']=base
    k=state.values['iteration'];logical=k+mode.get('base_logical_iteration',mode['legacy_persisted_iteration']) if mode['epoch'] else k
    metadata=dict(mode=mode,logical_iteration=logical,new_updates_this_run=stage.new_updates,
                  source_sha=stage.source,build_sources=stage.own_plan['legacy'][stage.family_name]['setup_source'],
                  last_audit=last_audit,counts=stage.packet.counts.copy(),audit_pending=bool(last_audit and last_audit.get('audit_pending')), 
                  started=stage.started.copy(),ledger_upper_reserved_actions=64)
    began=stage.begin_numeric_io()
    saved=store.save(arrays,metadata)
    stage.complete_numeric_io(began,saved['path'])
    return saved


def audit_point(stage,op,state,base,mode,store,*,name=None):
    rhs=stage.packet.a['b'];point=physical_point(op,state,rhs,base)
    actual=rhs-stage.packet.apply(point['z'])
    f=op.rhs(rhs) if base is None else op.pr(op.bar.reduced_rhs(rhs)-op.bar.apply(base))
    projected=f-op.apply(state.values['x'])
    identity_relative=float(np.linalg.norm(actual[:op.bar.n]-projected)/np.linalg.norm(rhs))
    estimate=abs(state.values['phibar']);truth=float(np.linalg.norm(projected))
    gap=abs(estimate-truth)/max(truth,estimate,1e-300)
    k=state.values['iteration'];logical=k+mode.get('base_logical_iteration',mode['legacy_persisted_iteration']) if mode['epoch'] else k
    family_directory=ARTIFACT_ROOT/stage.family_name
    directory=family_directory/'states'/stage.directory.name;directory.mkdir(parents=True,exist_ok=True)
    label=name or 'E'+str(mode['epoch'])+'_ITER_'+str(logical)
    arrays={key:point[key] for key in ('y','v','c','trace','port','z')};arrays['residual']=actual
    began=stage.begin_numeric_io()
    saved=atomic_arrays(directory/(label+'.npz'),**arrays)
    stage.complete_numeric_io(began,saved['path'])
    row=dict(logical_iteration=logical,epoch_iteration=k,mode=mode,source_sha=stage.source,state=saved,
             original_residual_identity_relative=identity_relative,estimated_residual_norm=estimate,
             true_projected_residual_norm=truth,recurrence_gap=gap,audit_pending=True,
             new_updates_this_run=stage.new_updates,Phi=float(.5*np.linalg.norm(actual)**2/np.linalg.norm(rhs)**2),
             action_counts=stage.packet.counts.copy())
    write_json(directory/(label+'.json'),row)
    save_gk(stage,store,state,base,mode,dict(row))
    audit=stage.audit(point['z']);gate=original_gate(audit)
    row.update(audit=audit,original_equation_gate=gate,audit_pending=False)
    write_json(directory/(label+'.json'),row);write_json(family_directory/'last_audit.json',row)
    with (family_directory/'audit_history.jsonl').open('a') as stream:stream.write(json.dumps(row)+'\n');stream.flush()
    save_gk(stage,store,state,base,mode,dict(row))
    stage.event('original_checkpoint_audit',library=stage.family_name,logical_iteration=logical,
                schur=audit['schur_relative'],native=audit['native_relative'],rho=gate['rho'],gap=gap)
    if identity_relative>1e-8 or max(audit['recovery_relative'],audit['schur_original_identity_operation_relative'])>1e-10:
        raise ValueError('original/projected/recovery identity failed')
    return row


def continue_route(stage):
    family=stage.family_name;pre,_=stage.io.read_result('PREFLIGHT')
    if not pre['libraries'].get(family,{}).get('qualified'):return dict(status='NOT_RUN_LIBRARY_INTERFACE',queue_frozen=True)
    began=time.perf_counter();op,loading=load_image(stage,stage.own_plan['images'][family])
    store,state,base,mode,manifest,errors=load_production(stage,family,op)
    target=stage.specification.derived['target_iteration'];initial_k=state.values['iteration']
    logical=lambda:state.values['iteration']+(mode.get('base_logical_iteration',mode['legacy_persisted_iteration']) if mode['epoch'] else 0)
    history=ARTIFACT_ROOT/family/'iteration_history.jsonl'
    row=audit_point(stage,op,state,base,mode,store);status='SLICE_COMPLETE'
    saved=row
    while logical()<target:
        budget=json.loads(stage.window.BUDGET_PATH.read_text())
        used=stage.base['routes'][family]['wall_seconds']+time.monotonic()-stage.run_started
        if used>budget['uniform_route_wall_seconds']-budget['GMRES_reserved_seconds']-60:
            status='LSQR_RESERVED_G_BOUNDARY';break
        stage.guard(extra_actions=8)
        if stage.base['routes'][family]['new_updates']+stage.new_updates>=8192:
            status='NEW_GK_BUDGET_STOP';break
        if row['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS':status='ORIGINAL_EQUATION_PASS';break
        if state.values['terminated']:status='BREAKDOWN_NOT_SOLVED';break
        state.step(op.apply,op.adjoint);stage.new_updates+=1
        with history.open('a') as stream:
            stream.write(json.dumps(dict(logical_iteration=logical(),epoch=mode['epoch'],
                estimated_residual_relative=abs(state.values['phibar'])/stage.packet.bnorm,
                new_updates_this_run=stage.new_updates,source_sha=stage.source))+'\n')
        if state.values['iteration']%16==0:save_gk(stage,store,state,base,mode,row)
        if logical()%64==0:
            row=audit_point(stage,op,state,base,mode,store);saved=row
            if row['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS':status='ORIGINAL_EQUATION_PASS';break
            records=[json.loads(s) for s in (ARTIFACT_ROOT/family/'audit_history.jsonl').read_text().splitlines()]
            # Gap must recur twice; one validated original-action correction
            # epoch is allowed, never an identity failure workaround.
            unique={a['logical_iteration']:a for a in records if not a['audit_pending']}
            recent=[unique[k] for k in sorted(unique)][-2:]
            if len(recent)==2 and all(a['recurrence_gap']>.1 for a in recent):
                if stage.base['routes'][family]['correction_restarts']>=1 or mode['epoch']>=1:
                    status='RECURRENCE_GAP_AFTER_ALLOWED_RESTART';break
                base=np.array(physical_point(op,state,stage.packet.a['b'],base)['trace'])
                mode=dict(mode,mode='RESIDUAL_CORRECTION_RESTART',epoch=1,base_logical_iteration=logical())
                stage.base['routes'][family]['correction_restarts']+=1
                f=op.pr(op.bar.reduced_rhs(stage.packet.a['b'])-op.bar.apply(base));state=LSQRState.initialize(op.adjoint,f)
                row=audit_point(stage,op,state,base,mode,store);journal('one_residual_correction_epoch',library=family,mode=mode)
            if logical()>=2048 and logical()%256==0:
                seq=[unique[k] for k in sorted(unique) if k%256==0 and k>=1280][-4:]
                if len(seq)==4 and all(1-seq[j+1]['original_equation_gate']['rho']/seq[j]['original_equation_gate']['rho']<.01 for j in range(3)):
                    status='LSQR_STAGNATION';break
    if saved['logical_iteration']!=logical():saved=audit_point(stage,op,state,base,mode,store)
    save_gk(stage,store,state,base,mode,saved)
    recomputed=max(0,min(logical(),mode['legacy_observed_iteration'])-mode['legacy_persisted_iteration'])
    correction_updates_this_run=stage.new_updates if mode['epoch'] else 0
    return dict(status=status,route=family,logical_iteration=logical(),legacy_observed_iteration=mode['legacy_observed_iteration'],
        legacy_persisted_iteration=mode['legacy_persisted_iteration'],resume_mode=mode,final=saved,
        new_updates_executed=stage.new_updates,recomputed_updates_in_this_lineage=recomputed,
        correction_epoch_updates_this_run=correction_updates_this_run,
        generation_errors_ignored=errors,loading_seconds=loading,route_accounted_wall_seconds=time.perf_counter()-began,
        bar_action_costs_inclusive_seconds=op.bar.costs.copy(),projection_triangular_inclusive_seconds=op.costs.copy(),
        nested_timers_additive=False,
        all_solver_states_frozen=True,queue_frozen=True,reference_read=False,hidden_training=False)


def gmres_route(stage):
    family=stage.family_name;directory=ARTIFACT_ROOT/family
    source=json.loads((directory/'last_audit.json').read_text());state=source['state']
    if source['audit_pending'] or file_hash(state['path'])!=state['sha256']:raise ValueError('no trusted GMRES base')
    with np.load(state['path'],allow_pickle=False) as stream:t=np.array(stream['trace'])
    bar=BarAction(ports_for(stage));rhs=stage.packet.a['b'];barb=bar.reduced_rhs(rhs)
    work=ARTIFACT_ROOT/('GMRES_'+family);work.mkdir(exist_ok=True)
    cycle_history=[];previous=work/'last_cycle.json'
    if previous.exists():
        last=json.loads(previous.read_text())
        if file_hash(last['state']['path'])!=last['state']['sha256']:raise ValueError('GMRES cycle hash differs')
        with np.load(last['state']['path']) as stream:t=np.array(stream['trace'])
        cycle_history=[json.loads(s) for s in (work/'cycles.jsonl').read_text().splitlines()]
    original_rho=cycle_history[0]['start_rho'] if cycle_history else source['original_equation_gate']['rho']
    status='GMRES_CYCLE_LIMIT';final=source
    for cycle in range(len(cycle_history)+1,17):
        budget=json.loads(stage.window.BUDGET_PATH.read_text())
        if stage.base['routes'][family]['wall_seconds']+time.monotonic()-stage.run_started>budget['uniform_route_wall_seconds']-60:
            status='GMRES_WALL_CONTROLLED_STOP';break
        if cycle>8 and (1-cycle_history[7]['original_equation_gate']['rho']/original_rho<.1):status='GMRES_NO_EXTENSION_PROGRESS';break
        stage.guard(extra_actions=70)
        stage.durable_counts(reserve=72)
        t,inner=correction_cycle(bar.apply,t,barb,stage.packet.bnorm)
        port=bar.close(t,rhs);z=np.r_[t,port];residual=rhs-stage.packet.apply(z)
        began=stage.begin_numeric_io()
        saved=atomic_arrays(work/('CYCLE_'+str(cycle)+'.npz'),trace=t,port=port,z=z,residual=residual)
        stage.complete_numeric_io(began,saved['path'])
        row=dict(cycle=cycle,source_sha=stage.source,state=saved,inner=inner,audit_pending=True,start_rho=original_rho)
        write_json(work/'last_cycle.json',row)
        # Bound a killed uncommitted cycle by 70 actions, not a 16-step GK gap.
        stage.durable_counts(reserve=72)
        audit=stage.audit(z);gate=original_gate(audit);row.update(audit=audit,original_equation_gate=gate,audit_pending=False)
        write_json(work/'last_cycle.json',row)
        with (work/'cycles.jsonl').open('a') as stream:stream.write(json.dumps(row)+'\n')
        cycle_history.append(row);final=row
        stage.event('GMRES_cycle_complete',library=family,cycle=cycle,iterations=inner['inner_iterations'],rho=gate['rho'])
        if gate['status']=='ORIGINAL_EQUATION_PASS':status='ORIGINAL_EQUATION_PASS';break
        if len(cycle_history)>=3:
            recent=cycle_history[-3:]
            if all(recent[j+1]['original_equation_gate']['rho']>recent[j]['original_equation_gate']['rho']*(1+1e-8) for j in range(2)):
                status='GMRES_TWO_CYCLE_INCREASE';break
    return dict(status=status,route='GMRES64-AFTER-'+family,final=final,cycles=cycle_history,
                Q_U_R_loaded=False,bar_action_costs_inclusive_seconds=bar.costs.copy(),
                nested_timers_additive=False,reference_read=False,queue_frozen=True,hidden_training=False)


def verify(stage):
    from src.io.neural_fe_continuation import read_index,V7_ROOT
    from src.runners.autonomous_neural_head import owned
    from src.solvers.neural_fe_blind_reference import independent_physics
    from src.runners.task042_experiment import thread_qualification
    if not (ARTIFACT_ROOT/'FROZEN.json').exists():raise ValueError('queue must freeze before reference')
    items=list(stage.own_plan['historical_baselines']);missing=[]
    for family in ('GPOLY','GNN'):
        directory=ARTIFACT_ROOT/family
        for k in (1024,2048):
            paths=sorted(directory.glob('states/*/E*_ITER_'+str(k)+'.json'))
            if paths:items.append(dict(json.loads(paths[-1].read_text()),name=family+'-'+str(k)))
            else:missing.append(family+'-'+str(k))
        for path,label in ((directory/'last_audit.json',family+'-LSQR-FINAL'),(ARTIFACT_ROOT/('GMRES_'+family)/'last_cycle.json',family+'-GMRES-FINAL')):
            if path.exists():items.append(dict(json.loads(path.read_text()),name=label))
    candidates={};sources={};seen=set()
    for item in items:
        if item.get('audit_pending'):
            # A frozen numeric state without completed audit can be audited
            # here; it is never mislabeled as an already qualified solution.
            missing.append(item['name']+' prior audit pending')
        path=Path(item['state']['path']).resolve()
        if not path.is_relative_to(stage.io.ROOT/'benchmarks/artifacts/task042') or file_hash(path)!=item['state']['sha256']:raise ValueError('frozen field identity differs')
        with np.load(path,allow_pickle=False) as stream:z=np.array(stream['z'])
        sha=array_hash(z)
        if sha in seen:continue
        seen.add(sha);candidates[item['name']]=z;sources[item['name']]=item
    if not 1<=len(candidates)<=12:raise ValueError('frozen field inventory exceeds limit')
    stage.event('all_solver_states_frozen_before_REF7',states=list(candidates))
    ref,_=read_index('blind_reference');path=owned(ref['reference_state'],V7_ROOT)
    if file_hash(path)!=stage.own_plan['reference_sha256']:raise ValueError('REF7 hash differs')
    with np.load(path,allow_pickle=False) as stream:reference=np.array(stream['z'])
    stage.meta['reference_arrays_read']=True
    stage.count('field_states',len(candidates));stage.count('original_audits',len(candidates)+1)
    physics,comparisons=independent_physics(stage.design,stage.packet,reference,candidates,stage.artifact)
    rows={name:physical_qualification(physics['rows'][name],comparisons[name],physics['reference_native_pass']) for name in candidates}
    return dict(status='FROZEN_VALIDATION_COMPLETE',rows=rows,states_read=len(candidates),missing=missing,
        state_sources=sources,reference_identity=ref['reference_state'],reference_audit=physics['rows']['REFERENCE']['audit'],
        reference_native_pass=physics['reference_native_pass'],reference_feedback_to_solver=False,
        no_new_solve=True,no_new_LU=True,threads=thread_qualification(),queue_frozen=True)
