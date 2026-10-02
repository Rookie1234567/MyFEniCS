"""Bounded geometric setup and one parameterized local/coarse cycle slice."""
import json
from pathlib import Path
from time import perf_counter,monotonic
import numpy as np

from src.solvers.local_block_coarse import (ROWS,FACTOR_STATUS,capacity,assemble_blocks,
    factor_blocks,LocalBlocks,LocalCoarse,composite_overlap)
from src.solvers.p1_image_minres import ImageMinres,IMAGE_STATUS
from src.solvers.p1_image_study import save_array
from src.solvers.p1_trace_study import bars,random
from src.solvers.augmented_trace_lsqr import operation_pair
from src.solvers.neural_fe_action_packet import array_hash,file_hash
from src.solvers.gmres_cycle_commit import close_point,cycle_commit
from src.runners.orthonormal_trace_reprofile import atomic_arrays
from src.runners.autonomous_neural_head import original_gate
from src.runners.task042_shared import write_json
from src.solvers.local_block_readiness import local_readiness,seal_local_ready


def load_state(stage,item,*,legacy=False):
    role='VERIFY' if stage.name=='VERIFY' else 'SETUP' if stage.name=='SETUP' else 'OWN_ZERO_'+stage.name if stage.name.endswith('Z') else 'WARM'
    return stage.io.physical_state(item,role=role,nt=stage.packet.nt,np_=stage.packet.np,size=stage.packet.size)


def mapping(stage):
    item=stage.own_plan['map'];path=Path(item['path']).resolve()
    if not path.is_relative_to(stage.io.ROOT/'benchmarks/artifacts/task042/v15') or file_hash(path)!=item['sha256']:raise ValueError('geometric map path/hash')
    with np.load(path,allow_pickle=False) as f:
        values={k:np.array(f[k]) for k in f.files}
    for k,v in values.items():
        if array_hash(v)!=item[k+'_sha256']:raise ValueError('geometric map member '+k)
    n=stage.packet.nt
    if not np.array_equal(values['row'],np.arange(n)) or not np.array_equal(values['master_native'],stage.packet.a['masters']):raise ValueError('map canonical master order')
    from src.solvers.local_trace_features import patch_ids,boxes
    groups,centers=patch_ids(values['physical_center'],stage.design['geometry']['bounds_nm'])
    if not np.array_equal(groups,values['patch_id']) or not np.array_equal(centers,values['periodic_representative_center']) or not np.array_equal(boxes(stage.design['geometry']['bounds_nm']),values['boxes']):raise ValueError('fixed geometric boxes/representative rule')
    entities={}
    for d,e,p in zip(values['entity_dim'],values['entity_id'],groups,strict=True):
        key=(int(d),int(e))
        if entities.setdefault(key,int(p))!=int(p):raise ValueError('entity split over blocks')
    counts=np.bincount(groups,minlength=8)
    if tuple(counts)!=ROWS or len(entities)!=2448:raise ValueError('geometric counts/entities changed')
    return groups,dict(map=item,canonical_rows=n,entity_count=len(entities),block_rows=counts.tolist(),
        all_member_hashes_checked=True,all_rows_exactly_once=True,slave_added=0,
        physical_center_rule_recomputed=True,neural_features_or_weights_read=False)


def load_image(stage):
    # No image is reconstructed; only original qualified T/U/R are loaded.
    T=stage.io.load_trace(stage.own_plan,stage.packet);values=[]
    for key in ('U','R'):
        item=stage.own_plan[key];path=Path(item['path']).resolve()
        if not path.is_relative_to(stage.io.ROOT/'benchmarks/artifacts/task042/v23') or file_hash(path)!=item['sha256']:raise ValueError('upstream '+key+' hash')
        v=np.load(path,mmap_mode='r',allow_pickle=False)
        if list(v.shape)!=item['shape'] or array_hash(v)!=item['array_sha256']:raise ValueError('image array identity')
        values.append(v)
    stage.meta['global_tall_image_QR_present']=True
    return ImageMinres(T,*values,count=stage.pc_count)


def local_checks(local,action,*,count=lambda k,n=1:None):
    from scipy.linalg import lu_solve
    rows=[]
    for b,(ids,A,factor) in enumerate(zip(local.rows,local.matrices,local.factors,strict=True)):
        for j in range(2):
            seed=422401+2*b+j;w=random(len(ids),seed);full=np.zeros(local.n,complex);full[ids]=w
            pair=operation_pair(A@w,action(full)[ids]);count('local_lu_solve');count('local_triangular_pass',2)
            x=lu_solve(factor,w,check_finite=False);error=float(np.linalg.norm(A@x-w))
            rows.append(dict(block=b,seed=seed,original_principal_action=pair,
                solve_relative=error/np.linalg.norm(w),solve_operation_relative=error/max(np.linalg.norm(A,1)*np.linalg.norm(x,1)+np.linalg.norm(w,1),1e-300)))
    r,s=random(local.n,422421),random(local.n,422422);a,b=.4+.7j,-.3+.5j
    x,y=local.apply(r),local.apply(s)
    repeat=operation_pair(local.apply(r),x);linear=operation_pair(local.apply(a*r+b*s),a*x+b*y)
    zero=bool(np.count_nonzero(local.apply(np.zeros(local.n,complex)))==0)
    row=dict(witnesses=rows,repeat=repeat,complex_linearity=linear,zero_exact=zero)
    row['qualified']=bool(zero and max(repeat['operation_relative'],linear['operation_relative'])<=1e-10
        and max(v['original_principal_action']['operation_relative'] for v in rows)<=1e-10
        and max(v['solve_relative'] for v in rows)<=1e-8 and max(v['solve_operation_relative'] for v in rows)<=1e-12)
    return row


def composite_checks(local,image,action,D):
    body=LocalCoarse(local,image,action);rows=[]
    from scipy.linalg import solve_triangular
    for j in range(3):
        w=random(image.T.shape[1],422431+j);r=random(local.n,422441+j)
        br=body.apply(r);balance=operation_pair(image.adjoint_image(action(br)),image.adjoint_image(r))
        expected=image.T@solve_triangular(image.R,D@w,check_finite=False)
        identity=operation_pair(body.apply(local.dop(image.T@w)),expected)
        rows.append(dict(seed=422431+j,coarse_balance=balance,LC_Dop_T=identity))
    r,s=random(local.n,422451),random(local.n,422452);a,b=.4+.7j,-.3+.5j
    x,y=body.apply(r),body.apply(s)
    repeat=operation_pair(body.apply(r),x);linear=operation_pair(body.apply(a*r+b*s),a*x+b*y)
    return dict(witnesses=rows,repeat=repeat,complex_linearity=linear,
        qualified=bool(max(v[k]['operation_relative'] for v in rows for k in ('coarse_balance','LC_Dop_T'))<=1e-8
        and max(repeat['operation_relative'],linear['operation_relative'])<=1e-10))


def setup(stage):
    groups,partition=mapping(stage)
    plan=capacity(partition['block_rows'],stage.packet.nt)
    write_json(stage.artifact/'local_capacity_before_allocation.json',plan)
    if not plan['qualified']:raise MemoryError('preallocation planning Gate')
    stage.pc_count('block_assemblies');old,fast=bars(stage)
    ids,A,assembly=assemble_blocks(stage.packet,groups,guard=stage.guard,event=stage.event)
    write_json(stage.artifact/'capacity_and_partition.json',dict(partition=partition,capacity=assembly['capacity']))
    result=dict(status='LOCAL_BLOCK_SETUP_COMPLETE',partition=partition,assembly=assembly,
        local_qualified=False,composite_qualified=False,warm_NPZ_decoded=False,reference_read=False,
        factor_status=FACTOR_STATUS,global_tall_image_QR_present=False)
    stage.partial_result=result;factors,safety=factor_blocks(A,count=stage.pc_count,guard=stage.guard)
    inventory=[]
    for b,(r,m,(lu,piv)) in enumerate(zip(ids,A,factors,strict=True)):
        work=stage.io.ARTIFACT_ROOT/'blocks';work.mkdir(exist_ok=True)
        item=dict(block=b,rows=r.tolist())
        for key,v in [('matrix',m),('LU',lu),('pivots',piv)]:item[key]=save_array(work/f'{b}_{key}.npy',v)
        inventory.append(item)
    result.update(factor_safety=safety,block_inventory=inventory)
    stage.meta['factor_status']=FACTOR_STATUS
    if not all(x['qualified'] for x in safety):return dict(result,stop_reason='FIXED_LOCAL_FACTOR_UNSAFE')
    local=LocalBlocks(stage.packet.nt,ids,A,factors,count=stage.pc_count)
    checks=local_checks(local,old.apply,count=stage.pc_count);result['local_checks']=checks
    if not checks['qualified']:return dict(result,stop_reason='LOCAL_PRINCIPAL_OR_SOLVE_GATE')
    pairs=[];x=random(stage.packet.size,422460)
    for adj in (False,True):pairs.append(dict(adjoint=adj,**operation_pair(stage.packet.apply(x,adjoint=adj),stage.fast.apply(x,adjoint=adj))))
    result['old_new_S_SH_pairs']=pairs
    if max(x['operation_relative'] for x in pairs)>1e-10:raise ValueError('original/class64 action mismatch')
    # Seal only after every public Gate. A failed partial SETUP may be indexed,
    # but neither the queue nor a standalone dat can trust its early flags.
    seal_local_ready(result,expected_map=stage.own_plan['map'])
    try:image=load_image(stage)
    except (OSError,ValueError) as e:return dict(result,composite_not_run_reason='UPSTREAM_T_U_R_UNAVAILABLE: '+str(e))
    result['global_tall_image_QR_present']=True
    D,overlap=composite_overlap(local,image,count=stage.pc_count,guard=stage.guard)
    result.update(D_L=save_array(stage.io.ARTIFACT_ROOT/'D_L.npy',D),composite_overlap=overlap)
    # Recheck images by three original actions, no new W or QR.
    pairs=[]
    for j in range(3):
        w=random(image.T.shape[1],422471+j)
        pairs.append(operation_pair(old.apply(image.T@w),image.U@(image.R@w)))
    result['reused_image_original_pairs']=pairs
    if max(v['operation_relative'] for v in pairs)>1e-10:raise ValueError('reused original image unsafe')
    if not overlap['qualified']:return dict(result,stop_reason='D_L_UNSAFE_LOCAL_ONLY_CONTINUES')
    result['composite_checks']=composite_checks(local,image,old.apply,D)
    result['composite_qualified']=result['composite_checks']['qualified']
    return result


def load_local(stage,setup,*,factor_root=None):
    # Explicit cross-batch read-only reuse; the default V24 ownership is intact.
    factor_root=(stage.io.ARTIFACT_ROOT/'blocks') if factor_root is None else Path(factor_root).resolve()
    stage.pc_count('factor_readers');ids=[];A=[];factors=[];checks=[]
    for b,item in enumerate(setup['block_inventory']):
        values={}
        for key in ('matrix','LU','pivots'):
            receipt=item[key];p=Path(receipt['path']).resolve()
            if not p.is_relative_to(factor_root) or file_hash(p)!=receipt['sha256']:raise ValueError('local block file hash')
            v=np.load(p,mmap_mode='r',allow_pickle=False)
            if list(v.shape)!=receipt['shape'] or array_hash(v)!=receipt['array_sha256']:raise ValueError('local block numeric hash')
            if v.flags.writeable:raise ValueError('factor reload must be read-only')
            values[key]=v
        ids.append(np.asarray(item['rows'],np.int64));A.append(values['matrix']);factors.append((values['LU'],np.array(values['pivots'],copy=True)))
        # Independent-process reload witnesses, no refactorization or fine action.
        from scipy.linalg import lu_solve
        for j in range(2):
            w=random(len(ids[-1]),422401+2*b+j);stage.pc_count('local_lu_solve');stage.pc_count('local_triangular_pass',2)
            x=lu_solve(factors[-1],w,check_finite=False);err=float(np.linalg.norm(A[-1]@x-w)/np.linalg.norm(w))
            if err>1e-8:raise ValueError('read-only local LU reload solve failed')
            checks.append(dict(block=b,seed=422401+2*b+j,relative=err))
    stage.meta.update(factor_status=FACTOR_STATUS,local_factors_read_only=True)
    return LocalBlocks(stage.packet.nt,ids,A,factors,count=stage.pc_count),dict(witnesses=checks,
        qualified=True,refactored=False,same_ABI=True,independent_process=True,source_sha=stage.source,
        readonly_factor_files=True,private_pivot_ABI_workspace_bytes=sum(piv.nbytes for _,piv in factors))


def route(stage):
    setup,_=stage.io.read_result('SETUP');name=stage.name;cold=name.endswith('Z');combo=name.startswith('LC')
    admission=local_readiness(setup,rows=tuple(stage.own_plan['local_specification']['rows']),expected_map=stage.own_plan['map'])
    if not admission['qualified']:return dict(status='NOT_RUN_PC_GATE',local_admission=admission)
    if combo and not setup.get('composite_qualified'):return dict(status='NOT_RUN_PC_GATE',reason='composite only',local_admission=admission)
    old,fast=bars(stage);local,reload=load_local(stage,setup)
    image=load_image(stage) if combo else None;body=LocalCoarse(local,image,fast.apply) if combo else local
    root=stage.io.ARTIFACT_ROOT/name;root.mkdir(exist_ok=True);rhs=stage.packet.a['b']
    parent=dict(name='ZERO_TRACE_FROM_FROZEN_OPERATOR',state=None) if cold else stage.own_plan['initial_states']['GPOLY']
    base=np.zeros(old.n,complex) if cold else load_state(stage,parent)['trace']
    initial_path=root/'initial.json'
    if initial_path.exists():start=json.loads(initial_path.read_text())
    else:
        arrays,identity=close_point(old,base,rhs);audit=stage.audit(arrays['z'])
        if not cold:
            prior=load_state(stage,parent)
            if np.linalg.norm(prior['residual']-arrays['residual'])/stage.packet.bnorm>1e-11:raise ValueError('warm saved residual identity')
        start=dict(state=atomic_arrays(root/'INITIAL.npz',**arrays),audit=audit,original_equation_gate=original_gate(audit),original_residual_identity_relative=identity)
        write_json(initial_path,start)
    history=[json.loads(p.read_text()) for p in sorted((root/'cycles').glob('CYCLE_*/commit.json'))]
    if any(r['cycle']!=j+1 or not r['committed'] or r['audit_pending'] for j,r in enumerate(history)):raise ValueError('route boundary inventory')
    t=load_state(stage,history[-1])['trace'] if history else base
    first=next((r['cycle'] for r in history if r['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS'),None)
    result=dict(status='ROUTE_COMPLETE',start=start,final=history[-1] if history else start,cycles=history,
        first_pass_cycle=first,parent=parent,PC_kind='LC8' if combo else 'L8',cold_parent_NPZ_decoded=False if cold else None,
        independent_reload=reload,reference_read=False,hidden_training=False,nested_timers_additive=False)
    stage.partial_result=result;stop='SLICE_TARGET_COMPLETE';maximum=32 if cold else 16;target=stage.specification.derived['target_cycles']
    for cycle in range(len(history)+1,min(maximum,target)+1):
        if first is not None and (history[-1]['original_equation_gate']['rho']<=1e-8 or cycle>first+2):stop='ORIGINAL_EQUATION_PASS';break
        if first is None and cycle>4 and (cycle-1)%4==0:
            previous=start['original_equation_gate']['rho'] if cycle==5 else history[cycle-6]['original_equation_gate']['rho']
            if 1-history[-1]['original_equation_gate']['rho']/previous<(.2 if cold else .1):stop='FIXED_PROGRESS_RULE_STOP';break
        if monotonic()-stage.run_started+stage.base['routes'].get(name,{}).get('wall_seconds',0)>stage.io.ROUTE_WALL[name]-60:stop='FIXED_ROUTE_WALL';break
        stage.reserve_cycle(pc=True);before=stage.actions();before_aux=stage.aux.copy();began=perf_counter()
        identity=dict(action_sha256=stage.own_plan['action_sha256'],physical_sha256=stage.own_plan['physical_sha256'],
            master_sha256=array_hash(stage.packet.a['masters']),map_sha256=stage.own_plan['map']['sha256'],
            block_inventory_sha256=setup['block_inventory_sha256'],window_sha256=file_hash(stage.window.WINDOW_PATH),route=name,
            PC=result['PC_kind'],U_sha256=stage.own_plan['U']['sha256'] if combo else None,R_sha256=stage.own_plan['R']['sha256'] if combo else None)
        from src.solvers.exact_action_recycle_study import OracleClosedBar
        row=cycle_commit(OracleClosedBar(fast,old),t,rhs,root/'cycles'/f'CYCLE_{cycle:04d}',identity,
            dict(cycle=cycle,source_sha=stage.source,input_sha256=stage.specification.input_sha256,parent_state=result['final']['state'],reference_arrays_read=False,cold_access_no_parent_arrays=cold),
            stage.audit,restart=256,preconditioner=body.apply,returned=stage.returned,residual_action=old.apply)
        stage.reserve=32;stage.pc_reserve=0;stage.durable();arrays=load_state(stage,row)
        delta=float(np.linalg.norm(stage.packet.apply(arrays['z'])-stage.fast.apply(arrays['z']))/stage.packet.bnorm)
        if delta>1e-11:raise ValueError('class64 original residual full-b difference')
        if row['original_residual_identity_relative']>1e-10:raise ValueError('original closure identity')
        row.update(cycle_action_count=stage.actions()-before,cycle_aux_counts={k:stage.aux[k]-before_aux[k] for k in stage.aux},cycle_inclusive_wall_seconds=perf_counter()-began,old_fast_residual_full_b_difference=delta)
        write_json(root/'cycles'/f'CYCLE_{cycle:04d}'/'commit.json',row);write_json(root/'last_cycle.json',row)
        history.append(row);t=arrays['trace'];result['final']=row
        if row['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS' and first is None:
            first=cycle;result['first_pass_cycle']=cycle;write_json(root/'FIRST_EQUATION_PASS.json',row)
        stage.event('local_cycle_complete',route=name,cycle=cycle,rho=row['original_equation_gate']['rho'],info=row['inner']['info'])
        if len(history)>=3 and all(history[-3+j+1]['audit']['schur_relative']>history[-3+j]['audit']['schur_relative']+max(1e-10,100*delta) for j in range(2)):
            repeat=stage.audit(arrays['z']);write_json(root/'two_increases_recheck.json',dict(audit=repeat))
            if repeat['schur_relative']>history[-2]['audit']['schur_relative']+max(1e-10,100*delta):stop='TWO_TRUE_RHO_INCREASES';break
    if len(history)>=4 and len(history)%4==0 and first is None:
        prior=start['original_equation_gate']['rho'] if len(history)==4 else history[-5]['original_equation_gate']['rho']
        if 1-history[-1]['original_equation_gate']['rho']/prior<(.2 if cold else .1):stop='FIXED_PROGRESS_RULE_STOP'
    if len(history)>=maximum:stop='FIXED_CYCLE_LIMIT'
    result.update(stop_reason=stop,L8_calls=local.calls,L8_inclusive_seconds=local.seconds,
        local_LU_solve_seconds=local.solve_seconds,LC8_inclusive_seconds=body.seconds if combo else None,
        R_solve_calls=image.calls if combo else 0,R_solve_seconds=image.seconds if combo else 0)
    return result
