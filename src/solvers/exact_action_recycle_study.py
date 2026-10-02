"""Finite exact-action qualification and same-origin recycled correction."""
import json
import shutil
from pathlib import Path
from time import perf_counter
import numpy as np
from src.runners.task042_shared import write_json
from src.runners.orthonormal_trace_reprofile import atomic_arrays
from src.runners.autonomous_neural_head import original_gate
from src.solvers.augmented_trace_lsqr import BarAction,operation_pair
from src.solvers.stable_head_varpro import PortBlocks
from src.solvers.local_trace_study import ports_for
from src.solvers.gmres_cycle_commit import close_point
from src.solvers.neural_fe_action_packet import array_hash,file_hash
from src.solvers import lgmres_boundary as lg
from src.solvers import gcrot_boundary as gc


def load_state(stage,item,*,legacy=False):
    state=item['state'];path=Path(state['path']).resolve()
    if not (path.is_relative_to(stage.io.ARTIFACT_ROOT) or path.is_relative_to(stage.io.ROOT/'benchmarks/artifacts/task042/v19')) or file_hash(path)!=state['sha256']:
        raise ValueError('V21 fixed state ownership/file hash differs')
    # Parent/verification reads physical state only; legacy Krylov vectors stay closed.
    with np.load(path,allow_pickle=False) as f:
        arrays={k:np.array(f[k]) for k in ('trace','port','z','residual') if k in f.files}
    for key,shape in [('trace',(stage.packet.nt,)),('port',(40,)),('z',(stage.packet.size,)),('residual',(stage.packet.size,))]:
        if key not in arrays or arrays[key].shape!=shape or not np.isfinite(arrays[key]).all():raise ValueError('V21 complete finite physical state missing')
        if key+'_sha256' in state and array_hash(arrays[key])!=state[key+'_sha256']:raise ValueError('V21 '+key+' array hash differs')
    if not np.array_equal(arrays['z'],np.r_[arrays['trace'],arrays['port']]):raise ValueError('V21 trace/port canonical inventory')
    return arrays


def bars(stage, *, fast=False):
    ports=ports_for(stage);oracle=BarAction(ports)
    candidate=BarAction(PortBlocks(stage.attach_fast(),ports.columns)) if fast else oracle
    return oracle,candidate


class OracleClosedBar:
    """Old close/oracle with frozen solver apply, for the existing LGMRES writer."""
    def __init__(self,solver,oracle):
        self.apply=solver.apply;self.close=oracle.close;self.reduced_rhs=oracle.reduced_rhs
        self.packet=oracle.packet
        self.n=oracle.n


def physical_point(stage,bar,trace,path):
    arrays,difference=close_point(bar,trace,stage.packet.a['b'])
    state=atomic_arrays(path,**arrays)
    audit=stage.audit(arrays['z'])
    return dict(state=state,audit=audit,original_equation_gate=original_gate(audit),
                original_residual_identity_relative=difference)


def preflight(stage):
    started=perf_counter();packet=stage.packet;rhs=packet.a['b']
    oracle,fast=bars(stage,fast=True)
    parents={key:load_state(stage,item,legacy=True) for key,item in stage.own_plan['initial_states'].items()}
    witnesses=[]
    for seed in (422101,422102):
        rng=np.random.default_rng(seed);z=rng.normal(size=packet.size)+1j*rng.normal(size=packet.size)
        witnesses.append(('random'+str(seed),z/np.linalg.norm(z)))
    for key,a in parents.items():
        witnesses.extend([(key+'-warm',a['z']),(key+'-residual',rhs-packet.apply(a['z']))])
    witnesses.append(('zero',np.zeros(packet.size,complex)))
    pairs=[];dots=[]
    for name,z in witnesses:
        row=dict(name=name)
        for adj in (False,True):
            a=packet.apply(z,adjoint=adj);b=stage.fast.apply(z,adjoint=adj)
            row['SH' if adj else 'S']=operation_pair(b,a)
        row['residual_difference_full_b']=float(np.linalg.norm(stage.fast.apply(z)-packet.apply(z))/packet.bnorm)
        if name.endswith('-warm'):row['old_original_audit']=stage.audit(z)
        pairs.append(row)
    x=witnesses[0][1][:packet.nt];y=witnesses[1][1][:packet.nt]
    left=np.vdot(y,fast.apply(x));right=np.vdot(fast.adjoint(y),x)
    dual_scale=np.linalg.norm(y)*np.linalg.norm(fast.apply(x))+np.linalg.norm(fast.adjoint(y))*np.linalg.norm(x)
    dots.append(dict(operation_relative=float(abs(left-right)/max(dual_scale,np.finfo(float).tiny))))
    bar_pairs=[dict(S=operation_pair(fast.apply(z[:packet.nt]),oracle.apply(z[:packet.nt])),
                    SH=operation_pair(fast.adjoint(z[:packet.nt]),oracle.adjoint(z[:packet.nt]))) for _,z in witnesses[:2]]
    qualified=(all(r[k]['operation_relative']<=1e-10 for r in pairs for k in ('S','SH'))
        and all(r['residual_difference_full_b']<=1e-11 for r in pairs if r['name'].endswith('-warm'))
        and dots[0]['operation_relative']<=1e-10
        and all(r[k]['operation_relative']<=1e-10 for r in bar_pairs for k in ('S','SH')))
    costs=[];whole={};selected='OLD_ACTION'
    if qualified:
        z=witnesses[0][1]
        for group in range(3):
            row=dict(group=group,order=['OLD_ACTION','EXACT_CLASS_BATCH64'] if group%2==0 else ['EXACT_CLASS_BATCH64','OLD_ACTION'])
            for key in row['order']:
                action=packet if key=='OLD_ACTION' else stage.fast
                action.apply(z);action.apply(z,adjoint=True)
                began=perf_counter()
                for _ in range(10):action.apply(z);action.apply(z,adjoint=True)
                row[key+'_seconds']=perf_counter()-began
            costs.append(row)
        tb=parents['GPOLY']['trace'];rb=oracle.reduced_rhs(rhs)-oracle.apply(tb)
        for key,solver in [('OLD_ACTION',oracle),('EXACT_CLASS_BATCH64',fast)]:
            stage.reserve_cycle();began=perf_counter()
            x,dirs,inner=lg.boundary_call(solver.apply,rb,np.zeros_like(tb),[],packet.bnorm)
            stage.returned(inner)
            arrays,identity=close_point(oracle,tb+x,rhs);audit=stage.audit(arrays['z'])
            whole[key]=dict(wall_seconds=perf_counter()-began,inner=inner,audit=audit,
                identity_relative=identity,test_update_not_used_as_formal_initial=True)
        ratio=whole['EXACT_CLASS_BATCH64']['wall_seconds']/whole['OLD_ACTION']['wall_seconds']
        if ratio<=.8:selected='EXACT_CLASS_BATCH64'
    else:ratio=None
    repeat=packet.apply(parents['GPOLY']['z']);repeat2=packet.apply(parents['GPOLY']['z'])
    repeat_difference=float(np.linalg.norm(repeat-repeat2)/packet.bnorm)
    choice=dict(selected_backend=selected,math_qualified=qualified,full_call_wall_ratio=ratio,
        choice_rule='math Gate plus at least 20% lower complete-call wall; otherwise OLD_ACTION',
        backend_frozen_before_formal_solve=True,reference_read=False,
        repeated_old_action_difference_full_b=repeat_difference)
    write_json(stage.io.ARTIFACT_ROOT/'BACKEND_CHOICE.json',choice)
    return dict(status='ACTION_QUALIFICATION_COMPLETE',equivalence=pairs,bar_pairs=bar_pairs,dot_tests=dots,
        capacity=stage.fast.metadata,paired_kernel_cost=costs,complete_call_cost=whole,
        backend_choice=choice,numerical_preflight_seconds=perf_counter()-started,
        original_oracle_unchanged=True,no_test_initial_reused=True)


def thin_numeric_state(row,arrays,path):
    """Keep compact physical history; large recycle workspace only last 2 calls."""
    core={key:arrays[key] for key in ('x','trace','port','z','residual') if key in arrays}
    row=dict(row,state=atomic_arrays(path,**core),returned_recycle_state=row['state'])
    return row


def route(stage):
    root=stage.io.ARTIFACT_ROOT;choice=json.loads((root/'BACKEND_CHOICE.json').read_text())
    if stage.name in ('T','Z'):
        primary,_=stage.io.read_result('C')
        gain=primary['start']['original_equation_gate']['rho']/primary['final']['original_equation_gate']['rho']
        if primary.get('first_pass_cycle') is None and gain<10:raise ValueError('V21 conditional C progress Gate not met')
    oracle,solver=bars(stage,fast=choice['selected_backend']=='EXACT_CLASS_BATCH64')
    rhs=stage.packet.a['b'];name=stage.name
    family='GNN' if name=='T' else 'GPOLY'
    parent=None if name=='Z' else stage.own_plan['initial_states'][family]
    tb=np.zeros(stage.packet.nt,complex) if parent is None else load_state(stage,parent,legacy=True)['trace']
    rb=oracle.reduced_rhs(rhs)-oracle.apply(tb)
    work=root/name;work.mkdir(parents=True,exist_ok=True)
    start_path=work/'START.json'
    if start_path.exists():start=json.loads(start_path.read_text())
    else:
        start=physical_point(stage,oracle,tb,work/'start.npz');write_json(start_path,start)
    cycles=[];x=np.zeros_like(tb);CU=[];directions=[];first=None;stop='CALL_LIMIT'
    history=work/'cycle_history.jsonl'
    if history.exists():
        cycles=[json.loads(s) for s in history.read_text().splitlines()]
        prior=cycles[-1]
        if first is None and (work/'FIRST_PASS.json').exists():first=json.loads((work/'FIRST_PASS.json').read_text())['cycle']
        resume=prior.get('returned_recycle_state',prior['state'])
        if file_hash(resume['path'])!=resume['sha256']:raise ValueError('V21 resume complete return hash')
        with np.load(resume['path'],allow_pickle=False) as f:arrays={k:np.array(f[k]) for k in f.files}
        x=arrays['x']
        if name=='B':directions=[(v,None) for v in arrays['outer_directions']]
        else:CU=gc.unpack_CU(arrays,len(tb))
    maxcalls=dict(B=16,C=128,T=64,Z=128)[name]
    action_cap=stage.io.ROUTE_ACTION[name];repeat=choice['repeated_old_action_difference_full_b']
    progress_threshold=.1 if name=='Z' else .05
    identity=dict(source_sha=stage.source,physical_sha256=stage.own_plan['physical_sha256'],
        action_sha256=stage.own_plan['action_sha256'],master_sha256=array_hash(stage.packet.a['masters']),
        backend=choice['selected_backend'],route=name)
    while len(cycles)<maxcalls:
        index=len(cycles)+1
        remaining=stage.window.snapshot()['heavy_remaining_seconds']
        prior_wall=stage.base['routes'].get(name,{}).get('wall_seconds',0.)
        if remaining<600 or prior_wall+perf_counter()-stage.began>stage.io.ROUTE_WALL[name]-90:
            stop='TIME_VERIFY_RESERVE_STOP';break
        if stage.base['routes'].get(name,{}).get('actions',0)+stage.actions()+384>action_cap:
            stop='ROUTE_ACTION_RESERVE_STOP';break
        if stage.carry_actions+stage.actions()+384>100000:stop='GLOBAL_ACTION_RESERVE_STOP';break
        if stage.counts['original_audits']+14>320:
            stop='GLOBAL_AUDIT_VERIFY_RESERVE_STOP';break
        if name!='B' and len(cycles)>=32 and len(cycles)%16==0:
            old=start if len(cycles)==32 else cycles[-17]
            # First 32 calls are always admitted. Subsequent blocks compare last 16.
            old=cycles[-17] if len(cycles)>16 else start
            reduction=1-cycles[-1]['original_equation_gate']['rho']/old['original_equation_gate']['rho']
            if reduction<progress_threshold:stop='FIXED_BLOCK_PROGRESS_STOP';break
        stage.reserve_cycle();began=perf_counter();before=stage.actions()
        directory=work/'cycles'/f'CALL_{index:04d}'
        metadata=dict(stage.meta,cycle=index,source_sha=stage.source,reference_arrays_read=False)
        if name=='B':
            row=lg.boundary_commit(OracleClosedBar(solver,oracle),tb,rb,x,directions,rhs,directory,identity,metadata,stage.audit,
                returned=stage.returned)
            with np.load(row['state']['path'],allow_pickle=False) as f:
                arrays={k:np.array(f[k]) for k in f.files}
            x=arrays['x'];directions=[(v,None) for v in arrays['outer_directions']]
        else:
            row=gc.boundary_commit(solver,oracle,tb,rb,x,CU,rhs,directory,identity,metadata,stage.audit,returned=stage.returned)
            with np.load(row['state']['path'],allow_pickle=False) as f:
                arrays={k:np.array(f[k]) for k in f.files}
            x=arrays['x'];CU=gc.unpack_CU(arrays,len(tb))
            if index%8==0:
                row['recycle_check']=gc.recycle_check(oracle.apply,CU)
                if not row['recycle_check']['qualified']:raise ValueError('V21 original A*u recycle pair failed')
        if solver is not oracle:
            old_action=stage.packet.apply(arrays['z']);new_action=stage.fast.apply(arrays['z'])
            row['old_new_residual_difference_full_b']=float(np.linalg.norm(old_action-new_action)/stage.packet.bnorm)
            if row['old_new_residual_difference_full_b']>1e-11:raise ValueError('V21 frozen backend quarantined by residual Gate')
        row.update(cycle=index,call_wall_seconds=perf_counter()-began,call_equivalent_actions=stage.actions()-before)
        row=thin_numeric_state(row,arrays,directory/'physical.npz')
        write_json(directory/'compact_commit.json',row)
        with history.open('a') as f:f.write(json.dumps(row)+'\n');f.flush();__import__('os').fsync(f.fileno())
        cycles.append(row);stage.reserve=32;stage.durable()
        # Only reconstructible V21 CU workspace is released. Physical history stays.
        if name!='B' and index>2:
            expired=work/'cycles'/f'CALL_{index-2:04d}'/'numeric'
            if expired.exists():shutil.rmtree(expired)
        stage.event('boundary_committed',cycle=index,rho=row['original_equation_gate']['rho'],
            info=row['inner']['info'],actual_bar_actions=row['inner']['actual_bar_actions'],recycle_inventory=len(CU) if name!='B' else len(directions))
        if row['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS' and first is None:
            first=index;write_json(work/'FIRST_PASS.json',row)
        if first is not None and (row['original_equation_gate']['rho']<=1e-8 or index>=first+8):
            stop='FIRST_PASS_POLISH_BOUNDARY';break
        if len(cycles)>=3:
            tolerance=max(1e-10,100*repeat)
            rises=[cycles[j]['original_equation_gate']['rho']-cycles[j-1]['original_equation_gate']['rho'] for j in (-1,-2)]
            if all(d>tolerance for d in rises):
                repeat_audit=stage.audit(arrays['z']);write_json(directory/'rise_recheck.json',repeat_audit)
                stop='TWO_CONSECUTIVE_ORIGINAL_RHO_RISES';break
    final=cycles[-1] if cycles else start
    result=dict(status='ROUTE_COMPLETE',method='RESET-LGMRES256-K3-CONTROL' if name=='B' else 'BOUNDARY-GCROT256-K32',
        parent=parent,initialization='ZERO_TRACE_FROM_FROZEN_OPERATOR' if name=='Z' else 'V19_FIXED_L_PARENT',
        start=start,final=final,cycles=cycles,first_pass_cycle=first,stop_reason=stop,
        backend=choice['selected_backend'],base_trace_sha256=array_hash(tb),fixed_rhs_sha256=array_hash(rb),
        reference_read=False,full_space_trace=True,old_CU_or_Q_loaded=False,
        neural_training_increment=False,global_factor_constructed=False,callback_is_not_Arnoldi=True)
    write_json(work/'route_summary.json',result)
    return result
