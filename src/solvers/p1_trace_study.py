"""V22 finite p1-origin coarse setup and independent full-space correction."""
import json
from pathlib import Path
from time import perf_counter,monotonic
import numpy as np
from scipy.sparse import save_npz,load_npz
from src.runners.task042_shared import write_json
from src.runners.orthonormal_trace_reprofile import atomic_arrays
from src.runners.autonomous_neural_head import original_gate
from src.solvers.augmented_trace_lsqr import BarAction,operation_pair
from src.solvers.stable_head_varpro import PortBlocks
from src.solvers.fixed_p3_ilu0 import direct_C
from src.solvers.gmres_cycle_commit import close_point,cycle_commit
from src.solvers.neural_fe_action_packet import array_hash,file_hash
from src.solvers.p1_trace_galerkin import RefinedCoarse,TraceGalerkinPC,assemble_coarse,FACTOR_STATUS


def load_state(stage,item,*,legacy=False):
    if stage.name=='Z':
        path=Path(item['state']['path']).resolve()
        allowed=(stage.io.ARTIFACT_ROOT/'Z',stage.artifact)
        if not any(path.is_relative_to(Path(root).resolve()) for root in allowed):
            raise ValueError('cold actor may only read its own returned physical states')
    return stage.io.physical_state(item,role='VERIFY' if stage.name=='VERIFY' else 'WARM',
        nt=stage.packet.nt,np_=stage.packet.np,size=stage.packet.size)


def bars(stage):
    packet=stage.packet;C=np.column_stack([direct_C(packet,np.eye(40,dtype=complex)[:,j]) for j in range(40)])
    columns=np.vstack([C,packet.a['Hhat']]);ports=PortBlocks(packet,columns)
    old=BarAction(ports);fast=BarAction(PortBlocks(stage.attach_fast(),columns))
    return old,fast


def random(n,seed):
    rng=np.random.default_rng(seed);v=rng.normal(size=n)+1j*rng.normal(size=n)
    return v/np.linalg.norm(v)


def pc_checks(stage,body,old):
    x,y=[random(old.n,seed) for seed in (422221,422222)]
    a,b=.7+.2j,-.3+.9j
    bx,by=body.apply(x),body.apply(y)
    repeat=operation_pair(body.apply(x),bx);linear=operation_pair(body.apply(a*x+b*y),a*bx+b*by)
    balances=[]
    for r in (x,y):
        q=body.Q(r);Ar=old.apply(q);restricted=body.TH@(r-Ar)
        scale=np.linalg.norm(body.TH@r)+np.linalg.norm(body.TH@Ar)
        balances.append(float(np.linalg.norm(restricted)/max(scale,1e-300)))
    out=dict(repeat=repeat,complex_linearity=linear,coarse_balance_operation_relative=balances,
        tau=body.tau,full_space_term_present=True,PC_is_not_an_accurate_fine_inverse=True)
    out['qualified']=bool(max(repeat['operation_relative'],linear['operation_relative'])<=1e-10 and max(balances)<=1e-8)
    return out


def setup(stage):
    old,fast=bars(stage);rhs=stage.packet.a['b'];parent=stage.own_plan['initial_states']['GPOLY']
    prior=load_state(stage,parent);arrays,diff=close_point(old,prior['trace'],rhs);audit=stage.audit(arrays['z'])
    old_fast=float(np.linalg.norm(stage.packet.apply(arrays['z'])-stage.fast.apply(arrays['z']))/stage.packet.bnorm)
    saved=float(np.linalg.norm(arrays['residual']-prior['residual'])/stage.packet.bnorm)
    library=dict(state=atomic_arrays(stage.artifact/'WARM_RECHECK.npz',**arrays),parent=parent,audit=audit,
        original_equation_gate=original_gate(audit),saved_residual_full_b_difference=saved,
        old_fast_residual_full_b_difference=old_fast,original_residual_identity_relative=diff,
        qualified=bool(saved<=1e-11 and old_fast<=1e-11 and max(audit['recovery_relative'],audit['schur_original_identity_operation_relative'])<=1e-10 and audit['slave_storage_max']==0))
    result=dict(status='P1_TRACE_SETUP_COMPLETE',warm=library,PC_qualified=False,transfer_qualified=False,
        factor_status='NOT_CONSTRUCTED',coarse_name='P1_TRACE_GALERKIN')
    write_json(stage.artifact/'warm_interface.json',library)
    stage.partial_result=result
    if not library['qualified']:return dict(result,PC_stop='FIXED_WARM_IDENTITY_GATE_FAILED')
    from src.solvers.p1_trace_transfer import build_transfer
    stage.pc_count('transfer_builds')
    T,norms,checks=build_transfer(stage.design,stage.packet,guard=stage.guard,event=stage.event)
    write_json(stage.artifact/'transfer_checks.json',checks);result['transfer_checks']=checks
    result['transfer_qualified']=checks['qualified']
    if not checks['qualified']:return dict(result,PC_stop='P1_TRANSFER_MATH_GATE_FAILED')
    path=stage.io.ARTIFACT_ROOT/'T.npz';save_npz(path,T,compressed=False)
    result['T']=dict(path=str(path),sha256=file_hash(path),shape=list(T.shape),canonical_master_sha256=array_hash(stage.packet.a['masters']))
    result['column_normalization']=atomic_arrays(stage.io.ARTIFACT_ROOT/'column_norms.npz',norms=norms)
    stage.pc_count('coarse_assemblies')
    Ac,receipt=assemble_coarse(stage.packet,T,guard=stage.guard,event=stage.event)
    path=stage.io.ARTIFACT_ROOT/'Ac.npy';np.save(path,Ac)
    result['Ac']=dict(path=str(path),sha256=file_hash(path),array_sha256=array_hash(Ac),shape=list(Ac.shape),capacity=receipt)
    witnesses=[]
    for j in range(8):
        w=random(T.shape[1],422211+j);expected=T.conj().T@old.apply(T@w)
        witnesses.append(dict(witness=j,seed=422211+j,**operation_pair(Ac@w,expected)))
    warm_restricted=T.conj().T@(old.reduced_rhs(rhs)-old.apply(prior['trace']))
    result['coarse_action_checks']=witnesses
    if max(r['operation_relative'] for r in witnesses)>1e-10:return dict(result,PC_stop='ORIGINAL_GALERKIN_ACTION_GATE_FAILED')
    stage.meta['factor_status']=FACTOR_STATUS
    result['factor_status']=FACTOR_STATUS
    from scipy.linalg import LinAlgWarning
    try:coarse=RefinedCoarse(Ac,count=stage.pc_count)
    except (ValueError,np.linalg.LinAlgError,LinAlgWarning) as error:
        return dict(result,PC_stop='FIXED_COARSE_LU_NEGATIVE',PC_error=str(error),factor_attempted=True)
    stage.meta['factor_status']=coarse.metadata['factor_status'];result['factor_status']=coarse.metadata['factor_status']
    coarse_checks=[]
    for j in range(8):
        s=warm_restricted if j==0 else random(len(Ac),422231+j)
        u=coarse.solve(s);error=np.linalg.norm(s-Ac@u)
        coarse_checks.append(dict(witness=j,relative=float(error/max(np.linalg.norm(s),1e-300)),
            operation_relative=float(error/max(np.linalg.norm(s)+np.linalg.norm(Ac,1)*np.linalg.norm(u,1),1e-300))))
    zero=coarse.solve(np.zeros(len(Ac),complex));result['coarse_LU']=coarse.metadata
    result['coarse_solve_checks']=coarse_checks;result['zero_coarse_exact']=bool(np.count_nonzero(zero)==0)
    if max(r['relative'] for r in coarse_checks)>1e-8 or max(r['operation_relative'] for r in coarse_checks)>1e-12 or not result['zero_coarse_exact']:
        return dict(result,PC_stop='FIXED_ONE_REFINEMENT_COARSE_SOLVE_NEGATIVE')
    body=TraceGalerkinPC(T,coarse,fast.apply,count=stage.pc_count)
    result['right_PC']=pc_checks(stage,body,old);result['PC_qualified']=result['right_PC']['qualified']
    result['coarse_solve_seconds']=coarse.seconds;result['PC_seconds_inclusive']=body.seconds
    return result


def load_PC(stage,setup,fast):
    for key in ('T','Ac'):
        item=setup[key];p=Path(item['path']).resolve()
        if not p.is_relative_to(stage.io.ARTIFACT_ROOT) or file_hash(p)!=item['sha256']:raise ValueError('V22 '+key+' identity differs')
    T=load_npz(setup['T']['path']);Ac=np.load(setup['Ac']['path'],allow_pickle=False)
    if array_hash(stage.packet.a['masters'])!=setup['T']['canonical_master_sha256'] or array_hash(Ac)!=setup['Ac']['array_sha256']:raise ValueError('V22 coarse/canonical numeric identity')
    coarse=RefinedCoarse(Ac,count=stage.pc_count)
    if coarse.metadata['LU_sha256']!=setup['coarse_LU']['LU_sha256'] or coarse.metadata['pivot_sha256']!=setup['coarse_LU']['pivot_sha256']:raise ValueError('V22 independent fixed LU differs')
    stage.meta['factor_status']=coarse.metadata['factor_status']
    body=TraceGalerkinPC(T,coarse,fast.apply,count=stage.pc_count)
    write_json(stage.artifact/'coarse_LU.json',coarse.metadata)
    return body


def route(stage):
    setup,_=stage.io.read_result('SETUP');name=stage.name;rhs=stage.packet.a['b']
    if name!='Z' and not setup['warm']['qualified']:return dict(status='NOT_RUN_WARM_INTERFACE')
    if name!='N' and not setup['PC_qualified']:return dict(status='NOT_RUN_FIXED_COARSE_GATE')
    if name=='T':
        primary,_=stage.io.read_result('P')
        if 'final' not in primary or not (primary['first_pass_cycle'] is not None or primary['start']['original_equation_gate']['rho']/primary['final']['original_equation_gate']['rho']>=5):return dict(status='NOT_RUN_TRANSFER_PROGRESS_GATE')
    old,fast=bars(stage);body=None
    if name=='Z':
        base=np.zeros(old.n,complex);parent=dict(name='ZERO_TRACE_FROM_FROZEN_OPERATOR',state=None)
    else:
        parent=stage.own_plan['initial_states']['GNN' if name=='T' else 'GPOLY'];base=load_state(stage,parent)['trace']
    if name!='N':body=load_PC(stage,setup,fast)
    checks=pc_checks(stage,body,old) if body else dict(qualified=True)
    if not checks['qualified']:raise ValueError('V22 PC linearity/original coarse balance failed')
    write_json(stage.artifact/'right_PC_checks.json',checks)
    arrays,identity=close_point(old,base,rhs);start_audit=stage.audit(arrays['z'])
    start=dict(state=atomic_arrays(stage.artifact/'INITIAL.npz',**arrays),audit=start_audit,
        original_equation_gate=original_gate(start_audit),original_residual_identity_relative=identity)
    work=stage.io.ARTIFACT_ROOT/name;work.mkdir(exist_ok=True);t=base.copy();history=[]
    for p in sorted((work/'cycles').glob('CYCLE_*/commit.json')):
        row=json.loads(p.read_text());load_state(stage,row)
        if not row['committed'] or row['audit_pending']:raise ValueError('V22 invalid saved boundary')
        history.append(row)
    if history:t=load_state(stage,history[-1])['trace']
    first=next((r['cycle'] for r in history if r['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS'),None)
    maximum=dict(N=4,P=16,Z=32,T=8)[name];stop='FIXED_CYCLE_LIMIT'
    for cycle in range(len(history)+1,maximum+1):
        if first is not None and (history[-1]['original_equation_gate']['rho']<=1e-8 or cycle>first+2):stop='ORIGINAL_EQUATION_PASS';break
        if first is None and cycle>4 and (cycle-1)%4==0 and name!='N':
            previous=start['original_equation_gate']['rho'] if cycle==5 else history[cycle-6]['original_equation_gate']['rho']
            if 1-history[-1]['original_equation_gate']['rho']/previous < (.2 if name=='Z' else .1):stop='FIXED_PROGRESS_RULE_STOP';break
        prior=stage.base['routes'].get(name,{}).get('wall_seconds',0.)
        if monotonic()-stage.run_started+prior>stage.io.ROUTE_WALL[name]-60:stop='FIXED_ROUTE_WALL';break
        stage.reserve_cycle(pc=body is not None);before=stage.actions();before_aux=stage.aux.copy();began=perf_counter()
        contract=dict(action_sha256=stage.own_plan['action_sha256'],physical_sha256=stage.own_plan['physical_sha256'],
            master_sha256=array_hash(stage.packet.a['masters']),window_sha256=file_hash(stage.window.WINDOW_PATH),
            route=name,T_sha256=setup.get('T',{}).get('sha256'),Ac_sha256=setup.get('Ac',{}).get('sha256'),
            PC='IDENTITY' if body is None else 'P1_TRACE_GALERKIN_FULL_SPACE',tau=body.tau if body else None)
        meta=dict(cycle=cycle,source_sha=stage.source,input_sha256=stage.specification.input_sha256,parent=parent,
            reference_arrays_read=False,coarse_name='P1_TRACE_GALERKIN',cold_access_no_parent_arrays=name=='Z')
        # Solver uses class64; close/residual/audit ALWAYS use the old oracle.
        from src.solvers.exact_action_recycle_study import OracleClosedBar
        solver=OracleClosedBar(fast,old)
        row=cycle_commit(solver,t,rhs,work/'cycles'/('CYCLE_'+str(cycle).zfill(4)),contract,meta,stage.audit,
            restart=256,preconditioner=body.apply if body else None,returned=stage.returned,residual_action=old.apply)
        stage.reserve=32;stage.pc_reserve=0;stage.durable()
        physical=load_state(stage,row);delta=float(np.linalg.norm(stage.packet.apply(physical['z'])-stage.fast.apply(physical['z']))/stage.packet.bnorm)
        if delta>1e-11:raise ValueError('V22 frozen class backend residual math gate failed')
        row.update(cycle_action_count=stage.actions()-before,cycle_aux_counts={k:stage.aux[k]-before_aux[k] for k in stage.aux},
            cycle_inclusive_wall_seconds=perf_counter()-began,old_fast_residual_full_b_difference=delta)
        write_json(work/'cycles'/('CYCLE_'+str(cycle).zfill(4))/'commit.json',row);write_json(work/'last_cycle.json',row)
        history.append(row);t=physical['trace']
        if row['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS' and first is None:
            first=cycle;write_json(work/'FIRST_EQUATION_PASS.json',row)
        stage.event('p1_trace_cycle_complete',route=name,cycle=cycle,rho=row['original_equation_gate']['rho'],info=row['inner']['info'])
        tolerance=max(1e-10,100*setup['warm']['old_fast_residual_full_b_difference'])
        if len(history)>=3 and all(history[-3+j+1]['audit']['schur_relative']>history[-3+j]['audit']['schur_relative']+tolerance for j in range(2)):
            write_json(work/'two_increases_recheck.json',dict(audit=stage.audit(physical['z']),threshold=tolerance));stop='TWO_TRUE_RHO_INCREASES';break
    final=history[-1] if history else start
    return dict(status='ROUTE_COMPLETE',stop_reason=stop,start=start,final=final,cycles=history,first_pass_cycle=first,parent=parent,
        initialization='ZERO_TRACE_FROM_FROZEN_OPERATOR' if name=='Z' else 'FIXED_PHYSICAL_PARENT',
        right_PC=checks,PC_kind='IDENTITY' if body is None else 'P1_TRACE_GALERKIN_FULL_SPACE',
        PC_apply_calls=body.calls if body else 0,PC_inclusive_seconds=body.seconds if body else 0,
        coarse_solve_calls=body.coarse.calls if body else 0,coarse_solve_seconds=body.coarse.seconds if body else 0,
        full_space_trace=True,no_Q_U_R_or_hidden_weights_loaded=True,hidden_training=False,reference_read=False,
        cold_parent_NPZ_decoded=False if name=='Z' else None,nested_timers_additive=False)
