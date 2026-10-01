"""Fixed R-parent original-equation P/L correction; no basis or GK load."""
import json
import time
from pathlib import Path
import numpy as np
from src.runners.task042_shared import write_json
from src.solvers.augmented_trace_lsqr import BarAction
from src.solvers.gmres_cycle_commit import cycle_commit
from src.solvers.lgmres_boundary import boundary_commit
from src.solvers.local_trace_study import ports_for
from src.solvers.neural_fe_action_packet import array_hash,file_hash


def load_state(stage,item,*,legacy=False):
    state=item['state'];path=Path(state['path']).resolve()
    allowed=stage.io.ROOT/'benchmarks/artifacts/task042'
    if not any(path.is_relative_to(allowed/v) for v in ('v18','v19')) or file_hash(path)!=state['sha256']:
        raise ValueError('V19 parent/own state ownership/hash differs')
    with np.load(path,allow_pickle=False) as f:
        arrays={k:np.array(f[k]) for k in ('trace','port','z','residual','x','outer_directions') if k in f.files}
    n=stage.packet.nt
    if any(k not in arrays or not np.isfinite(arrays[k]).all() for k in ('trace','port','z','residual')):
        raise ValueError('V19 complete finite state missing')
    if arrays['trace'].shape!=(n,) or arrays['port'].shape!=(40,) or arrays['z'].shape!=(n+40,) or arrays['residual'].shape!=(n+40,):
        raise ValueError('V19 trace/port/z/residual inventory differs')
    if not np.array_equal(arrays['trace'],arrays['z'][:n]) or not np.array_equal(arrays['port'],arrays['z'][n:]):
        raise ValueError('V19 close composition differs')
    if array_hash(arrays['z'])!=state['z_sha256']:raise ValueError('V19 z array hash differs')
    return arrays


def first_pass(stage,row):
    if row['original_equation_gate']['status']!='ORIGINAL_EQUATION_PASS':return
    path=stage.io.ARTIFACT_ROOT/('FIRST_PASS_'+stage.name+'.json')
    if not path.exists():write_json(path,dict(row,first_pass_source=stage.source))


def compact_cycle(row):
    return dict(cycle=row['cycle'],algorithm=row['algorithm'],library=row['library'],
        rho=row['original_equation_gate']['rho'],schur=row['audit']['schur_relative'],
        native=row['audit']['native_relative'],port=row['audit']['port_full_rhs_relative'],
        inner=row['inner'],state=row['state'],source_sha=row['source_sha'],
        counts=row.get('cycle_action_counts',{}),returned_boundary_resumed=row['returned_boundary_resumed'])


def route(stage):
    family,algorithm=stage.family_name,stage.algorithm_name
    pre,_=stage.io.read_result('PREFLIGHT')
    if not pre['libraries'].get(family,{}).get('qualified'):return dict(status='NOT_RUN_LIBRARY_INTERFACE')
    source=dict(stage.own_plan['initial_states'][family],original_equation_gate=pre['libraries'][family]['original_equation_gate'])
    original=load_state(stage,source);base=original['trace']
    bar=BarAction(ports_for(stage));rhs=stage.packet.a['b']
    work=stage.io.ARTIFACT_ROOT/stage.name;work.mkdir(exist_ok=True)
    history=[]
    for p in sorted((work/'cycles').glob('CYCLE_*/commit.json')):
        row=json.loads(p.read_text());load_state(stage,row)
        if not row['committed'] or row['audit_pending']:raise ValueError('invalid P/L commit')
        history.append(row)
    history.sort(key=lambda r:r['cycle'])
    if any(row['cycle']!=j+1 for j,row in enumerate(history)):raise ValueError('noncontiguous V19 boundaries')
    if algorithm=='L':
        p8=stage.io.ARTIFACT_ROOT/('P_'+family)/'cycles/CYCLE_0008/commit.json'
        # If a bounded P prefix exists but wall stopped before 8, it is still
        # not an eligible L0 per the registered schedule.
        if not p8.exists():return dict(status='NOT_RUN_P8_INCOMPLETE')
        if json.loads(p8.read_text())['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS':
            return dict(status='NOT_RUN_EQUATION_ALREADY_PASS')
    t=load_state(stage,history[-1])['trace'] if history else base.copy()
    rb=bar.reduced_rhs(rhs)-bar.apply(base) if algorithm=='L' else None
    if algorithm=='L' and history:
        last=load_state(stage,history[-1]);x=last['x'];directions=[(v,None) for v in last['outer_directions']]
    else:x=np.zeros(bar.n,complex);directions=[]
    first=next((r['cycle'] for r in history if r['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS'),None)
    final=history[-1] if history else source;status='SLICE_COMPLETE';target=stage.specification.derived['target_cycles']
    budget=json.loads(stage.window.BUDGET_PATH.read_text());prior=stage.base['routes'][stage.name]
    while len(history)<64:
        cycle=len(history)+1
        if first is not None:
            if final['original_equation_gate']['rho']<=1e-8 or cycle>min(64,first+2):status='ORIGINAL_EQUATION_PASS';break
        elif cycle>target:break
        if first is None and cycle>8 and (cycle-1)%8==0:
            start=source['original_equation_gate']['rho'] if cycle==9 else history[cycle-10]['original_equation_gate']['rho']
            drop=1-final['original_equation_gate']['rho']/start
            if drop<.05:status='SLOW_PROGRESS_BELOW_EXTENSION_RULE';break
        if prior['wall_seconds']+time.monotonic()-stage.run_started>budget['uniform_route_wall_seconds']-60:
            status='ROUTE_WALL_BOUNDARY';break
        directory=work/'cycles'/('CYCLE_'+str(cycle).zfill(4))
        returned_boundary=any((directory/'numeric').glob('slot*.commit.json'))
        needed=16 if returned_boundary else 320
        if prior['actions_upper']+stage.packet.counts['S']+stage.packet.counts['SH']+needed>19500:
            status='ROUTE_ACTION_BOUNDARY';break
        stage.guard(extra_actions=needed);stage.gmres_pending=not returned_boundary;stage.durable_counts()
        before=stage.packet.counts.copy();began=time.perf_counter()
        metadata=dict(cycle=cycle,algorithm=algorithm,library=family,source_sha=stage.source,
            input_sha256=stage.specification.input_sha256,start_rho=source['original_equation_gate']['rho'],
            parent_R_state=source['state'],parent_state=final['state'],reference_arrays_read=False)
        identity=dict(action_sha256=stage.own_plan['action_sha256'],physical_sha256=stage.own_plan['physical_sha256'],
            master_sha256=array_hash(stage.packet.a['masters']),window_sha256=file_hash(stage.window.WINDOW_PATH),
            algorithm_route=algorithm,library=family,parent_R_npz_sha256=source['state']['sha256'])
        kwargs=dict(returned=stage.gmres_returned,io_begin=stage.begin_numeric_io,io_done=stage.complete_numeric_io)
        if algorithm=='P':
            row=cycle_commit(bar,t,rhs,directory,identity,metadata,stage.audit,restart=256,**kwargs)
        else:
            row=boundary_commit(bar,base,rb,x,directions,rhs,directory,identity,metadata,stage.audit,**kwargs)
        stage.gmres_pending=False;stage.new_updates+=1;stage.durable_counts(reserve=0)
        row['cycle_action_counts']={k:stage.packet.counts[k]-before[k] for k in before}
        row['cycle_inclusive_wall_seconds']=time.perf_counter()-began
        # The numerical commit is already safe. These derived counts are then
        # added to its immutable cycle receipt, not to old V18 raw records.
        write_json(directory/'commit.json',row);write_json(work/'last_cycle.json',row)
        history.append(row);final=row;t=load_state(stage,row)['trace']
        if algorithm=='L':
            last=load_state(stage,row);x=last['x'];directions=[(v,None) for v in last['outer_directions']]
        first_pass(stage,row)
        if row['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS' and first is None:first=cycle
        stage.event('post_R_cycle_complete',algorithm=algorithm,library=family,cycle=cycle,
            rho=row['original_equation_gate']['rho'],info=row['inner']['info'],cycle_actions=row['cycle_action_counts'])
        tolerance=max(1e-10,100*pre['libraries'][family]['repeated_action_full_b_difference'])
        if len(history)>=3 and all(history[-3+j+1]['audit']['schur_relative']>history[-3+j]['audit']['schur_relative']+tolerance for j in range(2)):
            repeat=stage.audit(load_state(stage,final)['z'])
            write_json(work/'two_increases_recheck.json',dict(audit=repeat,original=row['audit'],threshold=tolerance))
            status='TWO_CYCLE_INCREASE';break
        if algorithm=='L' and not row['inner']['returned_update'] and first is None:
            status='NO_RETURNED_UPDATE';break
    if first is not None:status='ORIGINAL_EQUATION_PASS'
    return dict(status=status,final=final,start=source,start_rho=source['original_equation_gate']['rho'],
        cycles=[compact_cycle(r) for r in history],first_pass_cycle=first,
        Q_U_R_loaded=False,new_GK=False,hidden_training=False,reference_read=False,
        correction_form='sequential exact residual corrections' if algorithm=='P' else 'fixed rb; cumulative x; ordered own outer_v',
        bar_action_costs_inclusive_seconds=bar.costs.copy(),nested_timers_additive=False)
