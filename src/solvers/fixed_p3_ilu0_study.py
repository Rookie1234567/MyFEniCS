"""Finite V20 setup, independent original-equation routes and owned states."""
import json
from pathlib import Path
from time import perf_counter,monotonic
import numpy as np
from scipy.sparse import save_npz,load_npz
from src.runners.task042_shared import write_json
from src.runners.orthonormal_trace_reprofile import atomic_arrays
from src.runners.autonomous_neural_head import original_gate
from src.solvers.augmented_trace_lsqr import BarAction,operation_pair
from src.solvers.local_trace_study import ports_for
from src.solvers.gmres_cycle_commit import close_point,cycle_commit
from src.solvers.neural_fe_action_packet import array_hash,file_hash
from src.solvers.fixed_p3_ilu0 import capacity,assemble_K,direct_F,direct_C,NativeILU0,PortCorrected


def load_state(stage,item,*,legacy=False):
    state=item['state'];path=Path(state['path']).resolve();allowed=stage.io.ROOT/'benchmarks/artifacts/task042'
    if not (path.is_relative_to(stage.io.ARTIFACT_ROOT) or path.is_relative_to(allowed/'v19')) or file_hash(path)!=state['sha256']:
        raise ValueError('V20 state ownership/file hash differs')
    with np.load(path,allow_pickle=False) as f:
        arrays={k:np.array(f[k]) for k in ('trace','port','z','residual','y','By') if k in f.files}
    n=stage.packet.nt;p=stage.packet.np
    for k,shape in [('trace',(n,)),('port',(p,)),('z',(n+p,)),('residual',(n+p,))]:
        if k not in arrays or arrays[k].shape!=shape or not np.isfinite(arrays[k]).all():raise ValueError('V20 finite complete state inventory differs')
    if not np.array_equal(arrays['z'],np.r_[arrays['trace'],arrays['port']]) or array_hash(arrays['z'])!=state['z_sha256']:
        raise ValueError('V20 state canonical composition/hash differs')
    return arrays


def random_vector(n,seed):
    rng=np.random.default_rng(seed);v=rng.normal(size=n)+1j*rng.normal(size=n)
    return v/np.linalg.norm(v)


def pc_qualification(stage,body,K,*,cross_process=False):
    xs=[random_vector(stage.packet.nt,s) for s in (422001,422002)]
    answers=[body.apply(x) for x in xs];repeat=body.apply(xs[0]);a=.7+.2j;b=-.3+.9j
    linear=body.apply(a*xs[0]+b*xs[1]);pair=operation_pair(linear,a*answers[0]+b*answers[1])
    row=dict(repeat=operation_pair(repeat,answers[0]),complex_linearity=pair,
        approximate_inverse_relative=float(np.linalg.norm(xs[0]-K@answers[0])/np.linalg.norm(xs[0])),
        effective=body.metadata.copy(),approximate_inverse_is_not_accuracy_gate=True)
    path=stage.io.ARTIFACT_ROOT/'fixed_PC_fingerprint.npz'
    if cross_process:
        with np.load(path) as old:
            row['cross_process_pairs']=[operation_pair(answers[j],old['answer'+str(j)]) for j in range(2)]
    else:
        row['fingerprint']=atomic_arrays(path,answer0=answers[0],answer1=answers[1])
    row['qualified']=bool(row['repeat']['operation_relative']<=1e-10 and pair['operation_relative']<=1e-10
                          and all(p['operation_relative']<=1e-10 for p in row.get('cross_process_pairs',[])))
    if not row['qualified']:raise ValueError('V20 PC complex linearity/repeat/fingerprint failed')
    return row


def make_body(stage,K):
    stage.pc_count('factor_setups')
    body=NativeILU0(K,stage.artifact/'effective_pc_view.txt',count=stage.pc_count)
    stage.meta.update(global_p3_incomplete_factor_constructed=True,factor_status='GLOBAL_P3_INCOMPLETE_FACTOR_PRESENT')
    write_json(stage.artifact/'effective_pc_options.json',body.metadata)
    return body


def setup(stage):
    from petsc4py import PETSc
    bar=BarAction(ports_for(stage));rhs=stage.packet.a['b'];library={}
    for f,item in stage.own_plan['initial_states'].items():
        prior=load_state(stage,item);point,diff=close_point(bar,prior['trace'],rhs);audit=stage.audit(point['z'])
        saved_difference=float(np.linalg.norm(point['residual']-prior['residual'])/np.linalg.norm(rhs))
        repeated=float(np.linalg.norm((rhs-stage.packet.apply(point['z']))-point['residual'])/np.linalg.norm(rhs))
        state=atomic_arrays(stage.artifact/(f+'_closed.npz'),**point)
        library[f]=dict(qualified=diff<=1e-8 and saved_difference<=1e-8 and audit['port_operation_relative']<=1e-12
            and max(audit['recovery_relative'],audit['schur_original_identity_operation_relative'])<=1e-10 and audit['slave_storage_max']==0,
            state=state,audit=audit,original_equation_gate=original_gate(audit),
            saved_residual_full_b_difference=saved_difference,repeated_action_full_b_difference=repeated,parent=item['state'])
    plan=capacity(stage.packet,PETSc.IntType)
    result=dict(status='SETUP_COMPLETE',libraries=library,capacity=plan,PC_qualified=False,operator_qualified=False)
    write_json(stage.artifact/'capacity_before_allocation.json',plan)
    # N does not depend on the additional K/PC. A capacity/pivot failure must
    # not cancel a trustworthy matrix-free control.
    if not plan['qualified']:
        return dict(result,PC_stop='FIXED_ILU0_CAPACITY_NEGATIVE')
    stage.pc_count('K_assemblies')
    K,receipt=assemble_K(stage.packet,index_dtype=PETSc.IntType,guard=stage.guard,event=lambda **kw:stage.event(**kw))
    path=stage.io.ARTIFACT_ROOT/'K.npz';save_npz(path,K,compressed=False)
    result['K']=dict(path=str(path),sha256=file_hash(path),assembly=receipt)
    stage.meta.update(global_K_CSR_constructed=True,global_S_or_CSR_constructed=True,global_S_constructed=False,private_audit_CSR_constructed=False)
    base=load_state(stage,stage.own_plan['initial_states']['GPOLY'])
    vectors=[random_vector(bar.n,s) for s in (422001,422002)]+[base['trace'],base['residual'][:bar.n]]
    checks=[]
    for i,t in enumerate(vectors):
        full=stage.packet.apply(np.r_[t,np.zeros(40,complex)])
        dual=stage.packet.apply(np.r_[t,np.zeros(40,complex)],adjoint=True)
        k,kh=K@t,K.conj().T@t;stage.pc_count('F');F=direct_F(stage.packet,t)
        closed=k-bar.C@bar.solve_port(F);original=bar.apply(t)
        row=dict(vector=i,K=operation_pair(k,full[:bar.n]),KH=operation_pair(kh,dual[:bar.n]),
            F=operation_pair(F,full[bar.n:]),closed_difference_full_b=float(np.linalg.norm(closed-original)/np.linalg.norm(rhs)))
        checks.append(row)
    alpha=random_vector(40,422004);C=direct_C(stage.packet,alpha)
    col=stage.packet.apply(np.r_[np.zeros(bar.n,complex),alpha])
    ccheck=operation_pair(C,col[:bar.n]);hcheck=operation_pair(bar.ports.H@alpha,col[bar.n:])
    result['K_action_pairs']=checks;result['C_pair']=ccheck;result['H_pair']=hcheck
    result['operator_qualified']=bool(all(max(r['K']['operation_relative'],r['KH']['operation_relative'],r['F']['operation_relative'])<=1e-10
        and r['closed_difference_full_b']<=1e-8 for r in checks) and max(ccheck['operation_relative'],hcheck['operation_relative'])<=1e-10)
    write_json(stage.artifact/'K_action_pair.json',dict(checks=checks,C=ccheck,H=hcheck,qualified=result['operator_qualified']))
    if not result['operator_qualified']:return dict(result,PC_stop='ORIGINAL_K_PAIR_FAILED')
    body=None
    try:
        body=make_body(stage,K);result['PC']=pc_qualification(stage,body,K)
        result['PC_qualified']=True
    except Exception as error:
        result['PC_stop']='FIXED_ILU0_SETUP_NEGATIVE';result['PC_error']=type(error).__name__+': '+str(error)
        # Numeric pivot/backend failures are outcomes, not permission to tune.
        stage.event('fixed_PC_setup_negative',error=result['PC_error'])
    finally:
        if body is not None:body.destroy()
    return result


def route(stage):
    setup,_=stage.io.read_result('SETUP');name=stage.name;rhs=stage.packet.a['b']
    if not setup['libraries']['GPOLY']['qualified']:return dict(status='NOT_RUN_INITIAL_INTERFACE')
    if name!='N' and not setup['PC_qualified']:return dict(status='NOT_RUN_FIXED_PC_UNQUALIFIED')
    choice=None
    if name in ('T','C'):
        choice=json.loads((stage.io.ARTIFACT_ROOT/'PC_CHOICE.json').read_text())
        if not choice['admitted']:return dict(status='NOT_RUN_PC_PROGRESS_GATE')
    pc_kind='B40' if name=='P40' else 'B0'
    if choice:pc_kind=choice['pc_kind']
    family='GNN' if name=='T' else 'GPOLY'
    bar=BarAction(ports_for(stage));body=None;portpc=None;K=None
    if name=='C':
        # Never open old states in the cold worker; its only input arrays are
        # the frozen equation packet and original forty port columns.
        base=np.zeros(bar.n,np.complex128);stage.pc_count('K_assemblies')
        from petsc4py import PETSc
        K,krow=assemble_K(stage.packet,index_dtype=PETSc.IntType,guard=stage.guard,event=lambda **kw:stage.event(**kw))
        if krow['data_sha256']!=setup['K']['assembly']['data_sha256']:raise ValueError('cold original K numeric identity differs')
        write_json(stage.artifact/'cold_K_identity.json',krow)
        source=dict(name='ZERO_TRACE_FROM_FROZEN_OPERATOR',state=None)
    else:
        source=stage.own_plan['initial_states'][family];base=load_state(stage,source)['trace']
    if name!='N':
        if K is None:
            item=setup['K'];path=Path(item['path'])
            if file_hash(path)!=item['sha256']:raise ValueError('V20 shared K hash differs')
            K=load_npz(path)
        body=make_body(stage,K);write_json(stage.artifact/'PC_repeat_pair.json',pc_qualification(stage,body,K,cross_process=True))
        stage.meta.update(global_K_CSR_constructed=True,global_S_or_CSR_constructed=True,global_S_constructed=False,private_audit_CSR_constructed=False)
        if pc_kind=='B40':
            try:portpc=PortCorrected(body,bar.C,bar.ports.H,lambda t:direct_F(stage.packet,t),count=stage.pc_count)
            except ValueError as error:
                body.destroy();return dict(status='P40_NOT_RUN_PORT_CORRECTION_UNSAFE',error=str(error))
            write_json(stage.artifact/'port_correction.json',portpc.metadata)
    preconditioner=None if name=='N' else (portpc.apply if portpc else body.apply)
    start_arrays,diff=close_point(bar,base,rhs);start_audit=stage.audit(start_arrays['z'])
    start=dict(state=atomic_arrays(stage.artifact/'INITIAL.npz',**start_arrays),audit=start_audit,original_equation_gate=original_gate(start_audit))
    t=base.copy();history=[];first=None;status='FIXED_CYCLE_LIMIT';maximum=4 if name=='N' else 32 if name=='C' else 16
    block=8 if name=='C' else 4;progress=.2 if name=='C' else .1
    work=stage.io.ARTIFACT_ROOT/name;work.mkdir(exist_ok=True)
    for p in sorted((work/'cycles').glob('CYCLE_*/commit.json')):
        row=json.loads(p.read_text());load_state(stage,row)
        if not row['committed'] or row['audit_pending']:raise ValueError('invalid V20 prior complete boundary')
        history.append(row)
    if history:
        t=load_state(stage,history[-1])['trace']
        first=next((r['cycle'] for r in history if r['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS'),None)
    result={}
    try:
        for cycle in range(len(history)+1,maximum+1):
            if first is not None and (history[-1]['original_equation_gate']['rho']<=1e-8 or cycle>first+2):status='ORIGINAL_EQUATION_PASS';break
            if first is None and cycle>block and (cycle-1)%block==0 and name!='N':
                initial=start['original_equation_gate']['rho'] if cycle==block+1 else history[cycle-block-2]['original_equation_gate']['rho']
                if 1-history[-1]['original_equation_gate']['rho']/initial<progress:status='FIXED_PROGRESS_RULE_STOP';break
            prior=stage.base['routes'].get(name,{}).get('wall_seconds',0.)
            if monotonic()-stage.run_started+prior>stage.io.ROUTE_WALL[name]-60:status='FIXED_ROUTE_WALL';break
            stage.guard(extra_actions=320)
            stage.reserve=320;stage.durable();before=stage.packet.counts.copy();began=perf_counter()
            identity=dict(action_sha256=stage.own_plan['action_sha256'],physical_sha256=stage.own_plan['physical_sha256'],
                window_sha256=file_hash(stage.window.WINDOW_PATH),master_sha256=array_hash(stage.packet.a['masters']),
                parent_trace_sha256=array_hash(t),pc_kind='IDENTITY' if name=='N' else pc_kind,
                K_sha256=setup.get('K',{}).get('sha256'),factor_specification=body.metadata['specification'] if body else None)
            metadata=dict(cycle=cycle,algorithm=name,library=family,source_sha=stage.source,
                input_sha256=stage.specification.input_sha256,parent_state=source.get('state'),reference_arrays_read=False)
            row=cycle_commit(bar,t,rhs,work/'cycles'/('CYCLE_'+str(cycle).zfill(4)),identity,metadata,stage.audit,
                restart=256,preconditioner=preconditioner)
            stage.reserve=32;stage.durable()
            row['cycle_action_counts']={k:stage.packet.counts[k]-before[k] for k in before}
            row['cycle_inclusive_wall_seconds']=perf_counter()-began
            write_json(work/'cycles'/('CYCLE_'+str(cycle).zfill(4))/'commit.json',row)
            write_json(work/'last_cycle.json',row)
            history.append(row);t=load_state(stage,row)['trace']
            if row['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS' and first is None:
                first=cycle;write_json(work/'FIRST_PASS.json',row)
            stage.event('right_PC_cycle_complete',route=name,cycle=cycle,rho=row['original_equation_gate']['rho'],info=row['inner']['info'])
            tolerance=max(1e-10,100*setup['libraries'][family].get('repeated_action_full_b_difference',0.))
            if len(history)>=3 and all(history[-3+j+1]['audit']['schur_relative']>history[-3+j]['audit']['schur_relative']+tolerance for j in range(2)):
                write_json(work/'two_increases_recheck.json',dict(audit=stage.audit(load_state(stage,row)['z']),threshold=tolerance))
                status='TWO_CYCLE_SCHUR_INCREASES';break
        if first:status='ORIGINAL_EQUATION_PASS'
        result=dict(status=status,start=start,final=history[-1] if history else start,first_pass_cycle=first,
                    cycles=history,pc_kind='IDENTITY' if name=='N' else pc_kind,parent=source,
                    cold_kind='ZERO_TRACE_FROM_FROZEN_OPERATOR' if name=='C' else None,
                    hidden_training=False,Q_U_R_loaded=False,global_p4_factor_constructed=False,
                    reference_read=False,bar_action_costs_inclusive_seconds=bar.costs,nested_timers_additive=False)
    finally:
        if body:
            result.update(effective_pc=body.metadata,B0_apply_calls=body.calls,B0_apply_seconds=body.seconds)
            body.destroy()
        if portpc:result.update(port_correction=portpc.metadata,small_solve_calls=portpc.small_calls,small_solve_seconds=portpc.small_seconds,
                               auxiliary_F_seconds=portpc.F_seconds,auxiliary_F_calls=portpc.F_calls)
    return result
