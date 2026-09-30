"""V16 finite setup, full-space LSQR and frozen independent FE verification."""

import gc
import json
import time
from pathlib import Path

import numpy as np
from scipy.linalg import qr, svdvals

from src.io.augmented_trace_lsqr import ARTIFACT_ROOT, read_result
from src.io.orthonormal_trace_reprofile import read_frozen_state
from src.runners.autonomous_neural_head import original_gate
from src.runners.orthonormal_trace_reprofile import atomic_arrays
from src.runners.task042_shared import write_json
from src.solvers.augmented_trace_lsqr import BarAction, ProjectedTraceOperator, ThinBasis, operation_pair, projected_checks
from src.solvers.bounded_complex_lsqr import lsqr_steps
from src.solvers.local_trace_study import ports_for, physical_qualification
from src.solvers.neural_fe_action_packet import array_hash, file_hash
from src.solvers.stable_head_varpro import homogeneous_recovery_pair


def basis_for(stage, family):
    if family == 'ZERO':
        return ThinBasis(stage.packet.nt), dict(columns=0, canonical_master_sha256=array_hash(stage.packet.a['masters']))
    items = [stage.own_plan['G0'], stage.own_plan['complements'][family]]
    blocks = []
    for item in items:
        path = Path(item['path']).resolve()
        if not path.is_relative_to(stage.io.ROOT/'benchmarks/artifacts/task042') or file_hash(path) != item['sha256']:
            raise ValueError('frozen V15 basis missing or hash differs: '+str(path))
        b = np.load(path, mmap_mode='r', allow_pickle=False)
        if list(b.shape) != item['shape'] or b.dtype != np.complex128:
            raise ValueError('basis shape/type differs')
        columns = item.get('take_columns', b.shape[1])
        blocks.append(np.asfortranarray(b[:, :columns]))
        del b
    Q = ThinBasis(stage.packet.nt, blocks)
    if Q.shape != (18144, 3098):
        raise ValueError('full G0 plus common first1538 columns required')
    return Q, dict(G0=items[0], complement=items[1], columns=3098,
                   canonical_master_sha256=array_hash(stage.packet.a['masters']), both_contain_random_neural_G0=True)


def check_bar(stage, bar):
    rng = np.random.default_rng(421601); checks = []
    for _ in range(2):
        r = rng.normal(size=bar.n)+1j*rng.normal(size=bar.n)
        single, legacy = bar.adjoint(r), bar.ports.adjoint(r)
        checks.append(operation_pair(single, legacy))
    solve = []
    for _ in range(3):
        b = rng.normal(size=40)+1j*rng.normal(size=40);x = bar.solve_port(b)
        solve.append(float(np.linalg.norm(bar.ports.H@x-b)/(np.linalg.norm(bar.ports.H)*np.linalg.norm(x)+np.linalg.norm(b))))
    if max(c['operation_relative'] for c in checks)>1e-10 or max(solve)>1e-12:
        raise ValueError('single original SH adapter or Hhat solve differs')
    return dict(single_SH_vs_legacy_two_SH=checks, Hhat_condition=bar.ports.cond_H,
                Hhat_solve_operation_relative=solve, Hhat_not_Hp=True)


def build_image(stage, family):
    began = time.perf_counter(); stage.guard(large=True)
    Q, identity = basis_for(stage, family)
    bar = BarAction(ports_for(stage)); bar_checks = check_bar(stage, bar)
    n,r = Q.shape; orthQ = Q.orthogonality()
    if orthQ > 1e-10:
        raise ValueError('frozen trace Q is not orthogonal')
    stage.event('image_A_build_begin',family=family,columns=r)
    A = np.empty((n,r), dtype=complex, order='F')
    assembly_began = time.perf_counter()
    for start in range(0,r,32):
        stage.guard(extra_actions=min(32,r-start)); stage.count('new_A_columns',min(32,r-start))
        for j in range(start,min(start+32,r)):
            A[:,j] = bar.apply(Q.column(j))
        if start%128 == 0:stage.event('image_columns_completed',family=family,columns=min(start+32,r))
    assembly_seconds = time.perf_counter()-assembly_began
    A_hash, A_norm = array_hash(A), np.linalg.norm(A)
    stage.guard(large=True);stage.count('image_QR')
    qr_began=time.perf_counter();U,R=qr(A,mode='economic',overwrite_a=False,check_finite=False)
    qr_seconds=time.perf_counter()-qr_began
    total=0.
    for start in range(0,r,32):
        delta=U@R[:,start:start+32]-A[:,start:start+32]
        total+=float(np.linalg.norm(delta)**2)
    reconstruction=total**.5/max(A_norm,1e-300)
    del A;gc.collect()
    rank_began=time.perf_counter();singular=svdvals(R,check_finite=False)
    rank_seconds=time.perf_counter()-rank_began
    rank=int(np.sum(singular>1e-12*singular[0]))
    image=ThinBasis(n,[U]);del U;gc.collect()
    orthU=image.orthogonality()
    operator=ProjectedTraceOperator(bar,Q,image,R)
    pairings=[]
    for j in (0,1559,3097):
        c=np.zeros(r,complex);c[j]=1
        pairings.append(dict(column=j,**operation_pair(bar.apply(Q.forward(c)),image.forward(R@c))))
    for seed in (421601,421602):
        rng=np.random.default_rng(seed);c=rng.normal(size=r)+1j*rng.normal(size=r);c/=np.linalg.norm(c)
        pairings.append(dict(seed=seed,**operation_pair(bar.apply(Q.forward(c)),image.forward(R@c))))
    qualified=bool(rank==r and max(reconstruction,orthQ,orthU)<=1e-10
                   and max(x['operation_relative'] for x in pairings)<=1e-10)
    work=stage.artifact/('IMAGE_'+family);work.mkdir()
    np.save(work/'U.npy',image.blocks[0]);np.save(work/'R.npy',R)
    record=dict(family=family,basis_identity=identity,rank=rank,columns=r,
        singular_endpoints=[float(singular[-1]),float(singular[0])],relative_rank_threshold=1e-12,
        Q_orthogonality=orthQ,U_orthogonality=orthU,A_QR_reconstruction=reconstruction,
        A_sha256=A_hash,A_persisted=False,original_pairings=pairings,bar_checks=bar_checks,
        U=dict(path=str(work/'U.npy'),sha256=file_hash(work/'U.npy'),shape=[n,r]),
        R=dict(path=str(work/'R.npy'),sha256=file_hash(work/'R.npy'),shape=[r,r]),
        assembly_seconds=assembly_seconds,QR_seconds=qr_seconds,rank_check_seconds=rank_seconds,
        qualified=qualified,global_S_constructed=False,FE_factor_constructed=False)
    record['setup_seconds']=time.perf_counter()-began
    write_json(work/'image_checks.json',record)
    stage.event('image_setup_frozen',family=family,qualified=qualified,setup_seconds=record['setup_seconds'])
    return operator,record


def load_image(stage, record):
    began=time.perf_counter();Q,_=basis_for(stage,record['family'])
    arrays=[]
    for name in ('U','R'):
        item=record[name];path=Path(item['path']).resolve()
        if not path.is_relative_to(ARTIFACT_ROOT) or file_hash(path)!=item['sha256']:
            raise ValueError('image factor hash differs')
        arrays.append(np.load(path,allow_pickle=False))
    op=ProjectedTraceOperator(BarAction(ports_for(stage)),Q,ThinBasis(stage.packet.nt,[arrays[0]]),arrays[1])
    return op,time.perf_counter()-began


def algebra_witness(stage, op):
    rng=np.random.default_rng(421603);random=lambda n:rng.normal(size=n)+1j*rng.normal(size=n)
    v=op.pt(random(op.bar.n));v/=np.linalg.norm(v)
    c=random(op.Q.shape[1]);c/=max(np.linalg.norm(c),1.)
    port=random(40);port/=np.linalg.norm(port)
    known=np.r_[v+op.Q.forward(c),port]
    rhs=stage.packet.apply(known);physical_rhs_hash=array_hash(stage.packet.a['b'])
    recovered=op.restore(v,rhs)
    identity=operation_pair(op.rhs(rhs),op.apply(v))
    relative=float(np.linalg.norm(recovered['z']-known)/np.linalg.norm(known))
    residual=float(np.linalg.norm(rhs-stage.packet.apply(recovered['z']))/np.linalg.norm(rhs))
    homogeneous=homogeneous_recovery_pair(stage.packet,known,recovered['z'])
    if array_hash(stage.packet.a['b'])!=physical_rhs_hash:raise ValueError('physical b changed')
    result=dict(seed=421603,known_complement_norm=float(np.linalg.norm(v)),nonzero_port_norm=float(np.linalg.norm(port)),
                projected_identity=identity,known_z_relative=relative,manufactured_residual_relative=residual,
                homogeneous_recovery_operation_relative=homogeneous,
                manufactured_rhs_sha256=array_hash(rhs),physical_rhs_unchanged=True,
                iterative_manufactured_solve=False,reference_read=False,
                qualified=bool(max(relative,residual)<=1e-8 and homogeneous<=1e-10 and identity['operation_relative']<=1e-8))
    atomic_arrays(stage.artifact/'manufactured_algebra.npz',known_z=known,known_v=v,rhs=rhs,recovered_z=recovered['z'])
    return result


def preflight(stage):
    bar=BarAction(ports_for(stage));zero=ProjectedTraceOperator(bar,ThinBasis(stage.packet.nt))
    bar_checks=check_bar(stage,bar);zero_checks=projected_checks(zero,stage.packet.a['b'])
    del zero,bar;gc.collect()
    previous = None
    if (ARTIFACT_ROOT/'PREFLIGHT.json').exists():
        previous, previous_path = read_result('PREFLIGHT')
        image = dict(previous['augmented_setup'])
        if not image['qualified']:
            raise ValueError('failed image cannot be reused for an interface replay')
        op, loading = load_image(stage,image)
        image['setup_reuse'] = dict(path=str(previous_path),sha256=file_hash(previous_path),
            source_sha=previous['source_sha'],loading_seconds=loading,
            original_setup_seconds=image['setup_seconds'],A_or_QR_recomputed=False)
    else:
        op,image=build_image(stage,'GPOLY')
    checks=projected_checks(op,stage.packet.a['b']);witness=algebra_witness(stage,op)
    qualified=bool(zero_checks['qualified'] and image['qualified'] and checks['qualified'] and witness['qualified'])
    image['setup_seconds_with_projected_checks']=image['setup_seconds']
    # Account every POLY-specific check in its route wall, not only assembly.
    image['setup_seconds']=(previous['augmented_setup']['setup_seconds'] if previous else 0.)+time.perf_counter()-stage.began
    return dict(status='PROJECTED_OPERATOR_QUALIFIED' if qualified else 'PROJECTED_OPERATOR_FAILED',
                empty_Q_checks=zero_checks,bar_checks=bar_checks,augmented_setup=image,
                augmented_checks=checks,algebra_witness=witness,qualified=qualified,queue_frozen=True)


class RouteStop(RuntimeError):
    pass


def solve_route(stage):
    from src.solvers.augmented_trace_window import BUDGET_PATH
    pre,_=read_result('PREFLIGHT')
    if not pre.get('empty_Q_checks',{}).get('qualified'):
        return dict(status='NOT_RUN_EMPTY_Q_INTERFACE_GATE',queue_frozen=True)
    began=time.perf_counter();charged_setup=0.;loading=0.
    if stage.name=='ZERO':
        op=ProjectedTraceOperator(BarAction(ports_for(stage)),ThinBasis(stage.packet.nt))
        image=dict(columns=0,qualified=True,basis_identity=dict(columns=0))
    elif stage.name=='GPOLY':
        image=pre['augmented_setup']
        if not (image['qualified'] and pre['augmented_checks']['qualified'] and pre['algebra_witness']['qualified']):
            return dict(status='NOT_RUN_GPOLY_INTERFACE_GATE',queue_frozen=True)
        charged_setup=image['setup_seconds'];op,loading=load_image(stage,image)
    else:
        op,image=build_image(stage,'GNN')
        checks=projected_checks(op,stage.packet.a['b']);image['projected_checks']=checks
        if not (image['qualified'] and checks['qualified']):
            return dict(status='NOT_RUN_GNN_INTERFACE_GATE',setup=image,queue_frozen=True)
    budget=json.loads(BUDGET_PATH.read_text());B=budget['uniform_route_wall_seconds']
    original_baseline=stage.packet.counts['S']+stage.packet.counts['SH']
    # Setup is batch charged; the separate 13000 allowance is for iteration/audit.
    iteration_started=time.perf_counter();y=np.zeros(stage.packet.nt,complex)
    recurrence={};history=[];checkpoints=[];audit_history=[];last_iteration=0;estimated=None
    stop='MAX_ITERATIONS_CONTROLLED_STOP';last_point=None

    def actions():return stage.packet.counts['S']+stage.packet.counts['SH']
    def route_guard():
        stage.guard(extra_actions=16)
        if time.perf_counter()-began+charged_setup>B-30:
            raise RouteStop('ROUTE_WALL_CONTROLLED_STOP')
        if actions()-original_baseline>=12980:
            raise RouteStop('ROUTE_ACTION_CONTROLLED_STOP')

    def action(x):route_guard();return op.apply(x)
    def adjoint(x):route_guard();return op.adjoint(x)
    def completed(value):
        recurrence.clear();recurrence.update(value)

    def audit_point(k, current, save=False, final=False):
        nonlocal last_point
        point=op.restore(current,stage.packet.a['b'])
        actual=stage.packet.a['b']-stage.packet.apply(point['z'])
        projected=op.rhs(stage.packet.a['b'])-op.apply(current)
        identity=float(np.linalg.norm(actual[:stage.packet.nt]-projected)/np.linalg.norm(stage.packet.a['b']))
        point['residual']=actual
        # Minimal numerical packet is committed before metadata or audit.
        name=('FINAL' if final else 'ITER_'+str(k));saved=None
        if save or final:
            arrays={key:point[key] for key in ('y','v','c','trace','port','z','residual')}
            arrays.update({('GK_'+key):np.asarray(value) for key,value in recurrence.items()})
            arrays['iteration']=np.asarray(k);arrays['S_count']=np.asarray(stage.packet.counts['S']);arrays['SH_count']=np.asarray(stage.packet.counts['SH'])
            saved=atomic_arrays(stage.artifact/(name+'.npz'),**arrays)
        audit=stage.audit(point['z']);gate=original_gate(audit)
        row=dict(iteration=k,elapsed_seconds=time.perf_counter()-began+charged_setup,
            current_process_wall_seconds=time.perf_counter()-began,iteration_wall_seconds=time.perf_counter()-iteration_started,
            equivalent_actions_since_iteration_start=actions()-original_baseline,
            cumulative_packet_actions=actions(),estimated_residual_relative=(estimated/np.linalg.norm(stage.packet.a['b']) if estimated is not None else None),
            original_residual_identity_relative=identity,original_equation_gate=gate,audit=audit,
            Qc_norm=point['Qc_norm'],complement_norm=point['complement_norm'],
            Phi=float(.5*np.linalg.norm(actual)**2/np.linalg.norm(stage.packet.a['b'])**2),
            source_sha=stage.source,basis_identity=image['basis_identity'],state=saved,
            checkpoint_semantics='COMPLETE_GK_SNAPSHOT_NO_RESUME_ADAPTER' if recurrence else 'INITIAL_ZERO_ITERATION',
            resumable_claimed=False,final=final)
        if identity>1e-8 or not np.isfinite(point['z']).all():
            raise ValueError('original/projected residual identity failed or nonfinite')
        if saved:
            write_json(stage.artifact/(name+'_core.json'),row)
            checkpoints.append(row)
        audit_history.append(row);last_point=row
        with (stage.artifact/'audit_history.jsonl').open('a') as stream:stream.write(json.dumps(row)+'\n')
        stage.event('original_checkpoint_audit',route=stage.name,iteration=k,
            schur=audit['schur_relative'],native=audit['native_relative'],rho=gate['rho'],route_actions=actions()-original_baseline)
        return row

    initial=audit_point(0,y,save=True)
    if initial['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS':
        stop='ORIGINAL_EQUATION_PASS'
    else:
        f=op.rhs(stage.packet.a['b'])
        generator=lsqr_steps(action,adjoint,f,state_callback=completed)
        try:
            for k,current,estimate in generator:
                y=current;last_iteration=k;estimated=estimate
                if not np.isfinite(current).all() or not np.isfinite(estimate):raise ValueError('nonfinite Golub-Kahan state')
                row=dict(iteration=k,estimated_residual_relative=float(estimate/np.linalg.norm(stage.packet.a['b'])),
                    equivalent_actions=actions()-original_baseline,elapsed_seconds=time.perf_counter()-began+charged_setup)
                history.append(row)
                with (stage.artifact/'iteration_history.jsonl').open('a') as stream:stream.write(json.dumps(row)+'\n')
                if k%64==0:
                    checked=audit_point(k,y,save=k in (256,1024,2048))
                    if checked['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS':
                        if not checked['state']:audit_point(k,y,save=True)
                        stop='ORIGINAL_EQUATION_PASS';break
                    if k>=2048 and k%128==0:
                        window=[a for a in audit_history if a['iteration']%128==0][-4:]
                        if len(window)==4 and all(1-window[j+1]['original_equation_gate']['rho']/window[j]['original_equation_gate']['rho']<.001 for j in range(3)):
                            stop='STAGNATION_CONTROLLED_STOP';break
                if k>=4096:break
            else:
                stop='BREAKDOWN_NOT_SOLVED'
        except RouteStop as error:
            stop=str(error)
        finally:
            generator.close()
    final=audit_point(last_iteration,y,final=True)
    if final['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS':stop='ORIGINAL_EQUATION_PASS'
    return dict(status=stop,route=stage.name,initial=initial,final=final,checkpoints=checkpoints,
                image_setup=image,uniform_wall_budget=budget,prior_preflight_setup_charged_seconds=charged_setup,
                loading_seconds=loading,route_accounted_wall_seconds=time.perf_counter()-began+charged_setup,
                iteration_equivalent_actions=actions()-original_baseline,iteration_count=last_iteration,
                iteration_history=dict(path=str(stage.artifact/'iteration_history.jsonl'),rows=len(history)),
                audit_history=dict(path=str(stage.artifact/'audit_history.jsonl'),rows=len(audit_history)),
                bar_costs_seconds=op.bar.costs,projection_and_triangular_costs_seconds=op.costs,
                independent_y_zero_start=True,no_other_route_warm_start=True,queue_frozen=True,
                reference_read=False,hidden_training=False,full_complement_dimension=18144-image['columns'])


def verify(stage):
    from src.io.local_trace_representation import ARTIFACT_ROOT as OLD_ROOT
    from src.io.neural_fe_continuation import read_index,V7_ROOT
    from src.runners.autonomous_neural_head import owned
    from src.solvers.neural_fe_blind_reference import independent_physics
    from src.runners.task042_experiment import thread_qualification
    candidates,sources,missing={}, {}, [];seen=set();items=[]
    for old in stage.own_plan['historical_baselines']:
        items.append((old,OLD_ROOT))
    first_pass=[]
    for name in ('ZERO','GPOLY','GNN'):
        try:
            route,_=read_result(name)
        except FileNotFoundError:
            missing.append(dict(name=name,reason='missing route result'));continue
        if not route.get('queue_frozen'):raise ValueError('solver queue not frozen')
        if 'final' not in route:
            missing.append(dict(name=name,reason=route['status']));continue
        items.append((dict(route['final'],name=name+'-FINAL'),ARTIFACT_ROOT))
        cp=next((c for c in route['checkpoints'] if c['iteration']==1024),None)
        if cp:items.append((dict(cp,name=name+'-1024'),ARTIFACT_ROOT))
        else:missing.append(dict(name=name+'-1024',reason='iteration checkpoint not reached'))
        p=next((c for c in route['checkpoints'] if c['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS'),None)
        if p:first_pass.append((dict(p,name=name+'-FIRST-PASS'),ARTIFACT_ROOT))
    items.extend(first_pass[:2])
    for item,root in items:
        arrays=read_frozen_state(item['state'],root);identity=array_hash(arrays['z'])
        if identity in seen:continue
        seen.add(identity);candidates[item['name']]=arrays['z'];sources[item['name']]=item
    stage.event('all_solver_states_and_decisions_frozen_before_REF7',states=list(candidates))
    ref,_=read_index('blind_reference');path=owned(ref['reference_state'],V7_ROOT)
    if file_hash(path)!=stage.own_plan['reference_sha256']:
        return dict(status='REFERENCE_IDENTITY_UNRESOLVED',states_read=len(candidates),missing=missing,no_new_reference=True)
    with np.load(path,allow_pickle=False) as saved:reference=np.array(saved['z'])
    stage.meta['reference_arrays_read']=True
    if not 1<=len(candidates)<=10:raise ValueError('one to ten frozen validation states required')
    stage.count('field_states',len(candidates));stage.count('original_audits',len(candidates)+1)
    stage.guard(extra_actions=3*(len(candidates)+1),large=True)
    physics,comparisons=independent_physics(stage.design,stage.packet,reference,candidates,stage.artifact)
    reference_audit=dict(reference_identity=ref['reference_state'],audit=physics['rows']['REFERENCE']['audit'],
                         native_qualified=physics['reference_native_pass'],source_sha=stage.source)
    rows={name:physical_qualification(physics['rows'][name],comparisons[name],physics['reference_native_pass']) for name in candidates}
    return dict(status='FROZEN_VALIDATION_COMPLETE',rows=rows,states_read=len(candidates),missing=missing,
                state_sources=sources,reference_identity=ref['reference_state'],reference_audit=reference_audit,
                reference_only_after_solver_frozen=True,reference_feedback_to_solver=False,
                threads=thread_qualification(),no_new_solve=True,no_p4_enrichment=True)
