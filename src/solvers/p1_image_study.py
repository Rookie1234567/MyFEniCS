"""Finite same-space Galerkin/MR comparison and full-space right correction."""
import json,os
from pathlib import Path
from time import perf_counter,monotonic
import numpy as np

from src.runners.task042_shared import write_json
from src.runners.orthonormal_trace_reprofile import atomic_arrays
from src.runners.autonomous_neural_head import original_gate
from src.solvers.augmented_trace_lsqr import operation_pair
from src.solvers.gmres_cycle_commit import close_point,cycle_commit
from src.solvers.neural_fe_action_packet import array_hash,file_hash
from src.solvers.p1_trace_galerkin import RefinedCoarse
from src.solvers.p1_trace_study import bars,random
from src.solvers.p1_image_minres import build_image,decompose,ImageMinres,ImageMinresPC,IMAGE_STATUS,TAU


def save_array(path,value):
    temporary=path.with_suffix('.npy.partial')
    with temporary.open('wb') as f:np.save(f,value,allow_pickle=False);f.flush();os.fsync(f.fileno())
    os.replace(temporary,path)
    return dict(path=str(path),sha256=file_hash(path),array_sha256=array_hash(value),shape=list(value.shape),bytes=value.nbytes)


def load_state(stage,item,*,legacy=False):
    role='VERIFY' if stage.name=='VERIFY' else 'OWN_ZERO' if stage.name=='Z' else 'IMAGE_SETUP' if stage.name=='SETUP' else 'WARM'
    return stage.io.physical_state(item,role=role,nt=stage.packet.nt,np_=stage.packet.np,size=stage.packet.size)


def pc_checks(stage,body,old):
    x,y=[random(old.n,s) for s in (422321,422322)]
    a,b=.7+.2j,-.3+.9j
    bx,by=body.apply(x),body.apply(y)
    repeat=operation_pair(body.apply(x),bx);linear=operation_pair(body.apply(a*x+b*y),a*bx+b*by)
    balances=[operation_pair(body.image.adjoint_image(old.apply(v)),body.image.adjoint_image(r)) for r,v in ((x,bx),(y,by))]
    row=dict(repeat=repeat,complex_linearity=linear,UH_A_B_balance=balances,tau=body.tau,
        full_fine_direction_present=True,PC_is_not_an_accurate_fine_inverse=True)
    row['qualified']=bool(max(repeat['operation_relative'],linear['operation_relative'],*(r['operation_relative'] for r in balances))<=1e-10)
    return row


def setup(stage):
    # Deliberately no call to load_state, no parent NPZ read, no warm RHS.
    old,fast=bars(stage);T,Ac=stage.io.load_coarse(stage.own_plan,stage.packet)
    tau=float(np.sqrt(len(Ac))/np.linalg.norm(Ac,'fro'))
    if tau!=TAU:raise ValueError('frozen Ac/tau does not match V22')
    W,construction=build_image(T,fast.apply,count=stage.pc_count,guard=stage.guard,event=stage.event)
    Widentity=save_array(stage.io.ARTIFACT_ROOT/'W.npy',W)
    U,R,D,checks=decompose(W,T,Ac,count=stage.pc_count,guard=stage.guard)
    result=dict(status='IMAGE_SETUP_COMPLETE',construction=construction,decomposition=checks,
        W=Widentity,T=stage.own_plan['T'],Ac=stage.own_plan['Ac'],tau=tau,
        image_qualified=False,PC_qualified=False,warm_NPZ_decoded=False,reference_arrays_read=False)
    result['U']=save_array(stage.io.ARTIFACT_ROOT/'U.npy',U)
    result['R']=save_array(stage.io.ARTIFACT_ROOT/'R.npy',R)
    result['Dsmall']=save_array(stage.io.ARTIFACT_ROOT/'Dsmall.npy',D)
    stage.meta['factor_status']=IMAGE_STATUS
    stage.meta['global_tall_image_QR_present']=True;stage.partial_result=result
    if not checks['image_qualified']:
        return dict(result,stop_reason='FIXED_IMAGE_QR_R_SAFETY_GATE')
    image=ImageMinres(T,U,R,count=stage.pc_count)
    witnesses=[]
    for seed in stage.own_plan['witness_seeds']:
        w=random(T.shape[1],seed);t=T@w;expected=old.apply(t)
        c=image.coefficients(expected)
        witnesses.append(dict(seed=seed,W_original=operation_pair(W@w,expected),
            UR_original=operation_pair(U@(R@w),expected),JAT=operation_pair(T@c,t)))
    del W,D
    r=random(old.n,422311);c=image.coefficients(r);Ar=old.apply(T@c)
    residual=r-Ar;stationarity=float(np.linalg.norm(image.adjoint_image(residual))/max(np.linalg.norm(image.adjoint_image(r))+np.linalg.norm(image.adjoint_image(Ar)),1e-300))
    zero=image.apply(np.zeros(old.n,complex))
    old_new=[]
    v=random(stage.packet.size,422312)
    for adj in (False,True):old_new.append(dict(adjoint=adj,**operation_pair(stage.fast.apply(v,adjoint=adj),stage.packet.apply(v,adjoint=adj))))
    result.update(witnesses=witnesses,MR_stationarity_operation_relative=stationarity,
        zero_exact=bool(np.count_nonzero(zero)==0),old_class_action_pairs=old_new)
    result['image_qualified']=bool(checks['image_qualified'] and stationarity<=1e-8 and result['zero_exact']
        and max(row[k]['operation_relative'] for row in witnesses for k in ('W_original','UR_original','JAT'))<=1e-10
        and max(row['operation_relative'] for row in old_new)<=1e-10)
    if result['image_qualified'] and checks['full_space_PC_safe']:
        body=ImageMinresPC(image,fast.apply,count=stage.pc_count)
        result['right_PC']=pc_checks(stage,body,old);result['PC_qualified']=result['right_PC']['qualified']
    result.update(R_solve_calls=image.calls,R_solve_seconds=image.seconds,
                  qualification_extra_fine_actions=stage.actions()-T.shape[1])
    if result['qualification_extra_fine_actions']>160:raise RuntimeError('V23 qualification action cap')
    write_json(stage.artifact/'image_checks.json',result)
    return result


def load_image(stage,setup):
    T,Ac=stage.io.load_coarse(stage.own_plan,stage.packet)
    values=[]
    for key in ('U','R'):
        item=setup[key];path=Path(item['path']).resolve()
        if not path.is_relative_to(stage.io.ARTIFACT_ROOT) or file_hash(path)!=item['sha256']:raise ValueError('V23 '+key+' image file hash')
        value=np.load(path,mmap_mode='r',allow_pickle=False)
        if list(value.shape)!=item['shape'] or array_hash(value)!=item['array_sha256']:raise ValueError('V23 '+key+' numeric identity')
        values.append(value)
    stage.meta['factor_status']=IMAGE_STATUS;stage.meta['global_tall_image_QR_present']=True
    return ImageMinres(T,*values,count=stage.pc_count),Ac


def compare(stage):
    setup,_=stage.io.read_result('SETUP')
    if not setup['image_qualified']:return dict(status='NOT_RUN_IMAGE_GATE')
    old,fast=bars(stage);image,Ac=load_image(stage,setup)
    def G_count(key,n=1):stage.pc_count('G_triangular' if key=='coarse_triangular' else key,n)
    # G has the old exact one-refinement policy, only in this comparison.
    coarse=RefinedCoarse(Ac,count=G_count)
    if coarse.metadata['LU_sha256']!=stage.own_plan['coarse_LU_identity']['LU_sha256'] or coarse.metadata['pivot_sha256']!=stage.own_plan['coarse_LU_identity']['pivot_sha256']:raise ValueError('V23 old G fixed factor changed')
    stage.meta['bounded_G_factor_present']=True
    prior=load_state(stage,stage.own_plan['initial_states']['GPOLY']);rhs=stage.packet.a['b']
    closed,identity=close_point(old,prior['trace'],rhs)
    saved=float(np.linalg.norm(closed['residual']-prior['residual'])/stage.packet.bnorm)
    oldfast=float(np.linalg.norm(stage.fast.apply(closed['z'])-stage.packet.apply(closed['z']))/stage.packet.bnorm)
    initial_audit=stage.audit(closed['z']);warm=dict(state=atomic_arrays(stage.artifact/'INITIAL.npz',**closed),audit=initial_audit,
        original_equation_gate=original_gate(initial_audit),saved_residual_full_b_difference=saved,
        old_fast_residual_full_b_difference=oldfast,identity_relative=identity,
        qualified=bool(max(saved,oldfast)<=1e-11 and identity<=1e-10))
    if not warm['qualified']:raise ValueError('V23 warm identity failed in authorized D role')
    TH=image.T.conj().T.tocsr();barb=old.reduced_rhs(rhs)
    rows={};states={}
    for name,t in [('warm',prior['trace']),('zero',np.zeros(old.n,complex))]:
        r=barb-old.apply(t);cg=coarse.solve(TH@r);cm=image.coefficients(r)
        dg,dm=image.T@cg,image.T@cm;rg=r-old.apply(dg);rm=r-old.apply(dm)
        norms=[float(np.linalg.norm(v)) for v in (r,rg,rm)]
        row=dict(original_residual_norm=norms[0],G_residual_norm=norms[1],MR_residual_norm=norms[2],
            G_coefficient_norm=float(np.linalg.norm(cg)),MR_coefficient_norm=float(np.linalg.norm(cm)),
            G_trace_correction_norm=float(np.linalg.norm(dg)),MR_trace_correction_norm=float(np.linalg.norm(dm)),
            G_TH_residual_norm=float(np.linalg.norm(TH@rg)),MR_TH_residual_norm=float(np.linalg.norm(TH@rm)),
            G_UH_residual_norm=float(np.linalg.norm(image.adjoint_image(rg))),MR_UH_residual_norm=float(np.linalg.norm(image.adjoint_image(rm))),
            inequality_fixed_margin=1e-11*stage.packet.bnorm,
            minimum_residual_inequality=norms[2]<=min(norms[0],norms[1])+1e-11*stage.packet.bnorm)
        if not row['minimum_residual_inequality']:raise ValueError('IMAGE_MR_NUMERICAL_GATE_FAIL')
        if name=='warm':
            for method,correction,coefficient in [('G',dg,cg),('MR',dm,cm)]:
                arrays,diff=close_point(old,t+correction,rhs)
                state=atomic_arrays(stage.artifact/(method+'_WARM.npz'),**arrays,c=coefficient)
                audit=stage.audit(arrays['z']);point=dict(name='D-'+method,state=state,audit=audit,original_equation_gate=original_gate(audit),identity_relative=diff)
                actual=arrays['residual'][:stage.packet.nt];thin=r-image.U@(image.R@coefficient) if method=='MR' else r-old.apply(correction)
                delta=float(np.linalg.norm(actual-thin)/stage.packet.bnorm)
                point['actual_thin_residual_difference_full_b']=delta
                if delta>1e-11:raise ValueError('D actual physical residual vs thin image mismatch')
                states[method]=point
        row['classification']='SAME_SPACE_ONE_SHOT_LIMITATION' if norms[2]/norms[0]>.99 else 'ONE_SHOT_RESIDUAL_REDUCTION'
        rows[name]=row
    return dict(status='COARSE_COMPARISON_COMPLETE',warm=warm,comparison=rows,warm_corrections=states,
        G_factor=coarse.metadata,G_solve_calls=coarse.calls,G_solve_seconds=coarse.seconds,
        R_solve_calls=image.calls,R_solve_seconds=image.seconds,reference_read=False,
        D_corrections_not_solver_initial=True,normal_equations=False)


def route(stage):
    setup,_=stage.io.read_result('SETUP');name=stage.name;rhs=stage.packet.a['b']
    if not setup['PC_qualified']:return dict(status='NOT_RUN_IMAGE_PC_GATE')
    old,fast=bars(stage);image,_=load_image(stage,setup);body=ImageMinresPC(image,fast.apply,count=stage.pc_count)
    if name=='Z':base=np.zeros(old.n,complex);parent=dict(name='ZERO_TRACE_FROM_FROZEN_OPERATOR',state=None)
    else:parent=stage.own_plan['initial_states']['GPOLY'];base=load_state(stage,parent)['trace']
    checks=pc_checks(stage,body,old)
    if not checks['qualified']:raise ValueError('V23 original full-space PC balance failed')
    work=stage.io.ARTIFACT_ROOT/name;work.mkdir(parents=True,exist_ok=True)
    arrays,identity=close_point(old,base,rhs);audit=stage.audit(arrays['z'])
    start=dict(state=atomic_arrays(stage.io.ARTIFACT_ROOT/name/'INITIAL.npz',**arrays),audit=audit,
        original_equation_gate=original_gate(audit),original_residual_identity_relative=identity)
    t=base.copy();history=[]
    for p in sorted((work/'cycles').glob('CYCLE_*/commit.json')):
        row=json.loads(p.read_text());load_state(stage,row)
        if not row['committed'] or row['audit_pending']:raise ValueError('V23 invalid boundary')
        history.append(row)
    if history:t=load_state(stage,history[-1])['trace']
    first=next((r['cycle'] for r in history if r['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS'),None)
    maximum=32 if name=='Z' else 16;stop='FIXED_CYCLE_LIMIT'
    for cycle in range(len(history)+1,maximum+1):
        if first is not None and (history[-1]['original_equation_gate']['rho']<=1e-8 or cycle>first+2):stop='ORIGINAL_EQUATION_PASS';break
        if first is None and cycle>4 and (cycle-1)%4==0:
            previous=start['original_equation_gate']['rho'] if cycle==5 else history[cycle-6]['original_equation_gate']['rho']
            if 1-history[-1]['original_equation_gate']['rho']/previous<(.2 if name=='Z' else .1):stop='FIXED_PROGRESS_RULE_STOP';break
        if monotonic()-stage.run_started+stage.base['routes'].get(name,{}).get('wall_seconds',0)>stage.io.ROUTE_WALL[name]-60:stop='FIXED_ROUTE_WALL';break
        stage.reserve_cycle(pc=True);before=stage.actions();before_aux=stage.aux.copy();began=perf_counter()
        contract=dict(action_sha256=stage.own_plan['action_sha256'],physical_sha256=stage.own_plan['physical_sha256'],
            master_sha256=array_hash(stage.packet.a['masters']),window_sha256=file_hash(stage.window.WINDOW_PATH),route=name,
            T_sha256=setup['T']['sha256'],U_sha256=setup['U']['sha256'],R_sha256=setup['R']['sha256'],PC='P1_IMAGE_MINRES_FULL_SPACE',tau=body.tau)
        meta=dict(cycle=cycle,source_sha=stage.source,input_sha256=stage.specification.input_sha256,parent=parent,
            reference_arrays_read=False,cold_access_no_parent_arrays=name=='Z')
        from src.solvers.exact_action_recycle_study import OracleClosedBar
        row=cycle_commit(OracleClosedBar(fast,old),t,rhs,work/'cycles'/('CYCLE_'+str(cycle).zfill(4)),contract,meta,stage.audit,
            restart=256,preconditioner=body.apply,returned=stage.returned,residual_action=old.apply)
        stage.reserve=32;stage.pc_reserve=0;stage.durable()
        physical=load_state(stage,row);delta=float(np.linalg.norm(stage.packet.apply(physical['z'])-stage.fast.apply(physical['z']))/stage.packet.bnorm)
        if delta>1e-11:raise ValueError('V23 class backend residual gate failed')
        row.update(cycle_action_count=stage.actions()-before,cycle_aux_counts={k:stage.aux[k]-before_aux[k] for k in stage.aux},
            cycle_inclusive_wall_seconds=perf_counter()-began,old_fast_residual_full_b_difference=delta)
        write_json(work/'cycles'/('CYCLE_'+str(cycle).zfill(4))/'commit.json',row);write_json(work/'last_cycle.json',row)
        history.append(row);t=physical['trace']
        if row['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS' and first is None:first=cycle;write_json(work/'FIRST_EQUATION_PASS.json',row)
        stage.event('image_mr_cycle_complete',route=name,cycle=cycle,rho=row['original_equation_gate']['rho'],info=row['inner']['info'])
        if len(history)>=3 and all(history[-3+j+1]['audit']['schur_relative']>history[-3+j]['audit']['schur_relative']+max(1e-10,100*delta) for j in range(2)):
            write_json(work/'two_increases_recheck.json',dict(audit=stage.audit(physical['z'])));stop='TWO_TRUE_RHO_INCREASES';break
    return dict(status='ROUTE_COMPLETE',stop_reason=stop,start=start,final=history[-1] if history else start,cycles=history,
        first_pass_cycle=first,parent=parent,initialization='ZERO_TRACE_FROM_FROZEN_OPERATOR' if name=='Z' else 'FIXED_V21_C_FINAL',
        right_PC=checks,PC_kind='P1_IMAGE_MINRES_FULL_SPACE',B_M_apply_calls=body.calls,B_M_inclusive_seconds=body.seconds,
        R_solve_calls=image.calls,R_solve_seconds=image.seconds,nested_timers_additive=False,reference_read=False,
        hidden_training=False,no_old_neural_Q_or_directions_loaded=True,cold_parent_NPZ_decoded=False if name=='Z' else None)
