"""Thin V71 queue: packet, bounded PC, one FGMRES, original-field tail."""
import gc
import json
import os
import time
from pathlib import Path

import numpy as np

from src.runners.task042_shared import write_json
from . import bounded_trace_scope as scope
from . import independent_tetra_reference as core
from .scattering_anchor import Journal, relative, save_arrays
from .scattering_anchor_checks import checked_arrays
from .hot_tetra_trace import HotTracePacket
from .bounded_trace_pc import (csr_load, csr_save, geometric_patches,
    coarse_trace_embedding, coarse_galerkin, local_principal, prolong, restrict,
    BoundedTwoLevelPC)


def parent():return scope.plan_record()['prepared_parent']


def action_charge(kind,operation):
    """Write-ahead upper/lower counters across stages and failed calls."""
    p=scope.window.TMP/'action_counts.json'
    counts=json.loads(p.read_text()) if p.exists() else dict(started=0,completed=0,by_kind={})
    if counts['started']>=600:raise RuntimeError('V71 cumulative whole-action upper cap')
    counts['started']+=1;counts['by_kind'][kind]=counts['by_kind'].get(kind,0)+1
    write_json(p,counts)
    out=operation();counts['completed']+=1;write_json(p,counts);return out


def service(journal,s=None,b=None,oracle=None):
    p=parent();identity=None
    if s is not None:
        from .assembly_tetra_study import packet_identity
        identity=packet_identity(s,b,oracle)
    with journal.measured('cold_checked_local_packet_hot_maps_and_boundary_aggregate'):
        result=HotTracePacket(p['local_packet'],identity=identity)
    journal.owners('exact_hot_classes_maps_boundary',result)
    return result


def preflight(folder,journal):
    p=parent();a=service(journal);ref=checked_arrays(p['retained_action_witness'])
    errors=[];receipts=[];hot=[]
    for j in range(2):
        with journal.measured('hot_fixed_complex_action_'+str(j)):
            out=action_charge('O_fixed',lambda:a.apply_trace(ref['inputs'][:,j]))
        target=ref['outputs'][:,j]
        error=dict(FE=relative(out[:a.nt]-target[:a.nt],target[:a.nt]),
                   port=relative(out[a.nt:]-target[a.nt:],target[a.nt:]),full=relative(out-target,target))
        errors.append(error);receipts.append(save_arrays(folder/f'fixed{j}.npz',input=ref['inputs'][:,j],output=out,reference=target))
    for j in range(3):
        began=time.perf_counter();out=action_charge('O_hot_timing',lambda:a.apply_trace(ref['inputs'][:,j%2]))
        hot.append(time.perf_counter()-began)
    # Reuse only a preregistered arbitrary-RHS witness, never a reference field.
    w=checked_arrays(p['qualification']['arrays']);rhs=w['rhs'];t=w['retained'][:,0]
    with journal.measured('nonzero_internal_and_port_RHS_recover_condense_witness'):
        full=a.recover(t,rhs);reduced=a.condense_rhs(rhs)
        out=action_charge('O_rhs_identity',lambda:a.apply_trace(t))
        lifted=a.lift_residual(reduced-out)
    witness=dict(recovery=relative(full-w['full'][:,0],w['full'][:,0]),
        original_operation=relative(lifted-w['original_residual'][:,0],w['original_action'][:,0]),
        internal_and_port_nonzero=bool(np.any(rhs[:a.n]) and np.any(rhs[a.n:])),
        original_witness_source=p['qualification']['arrays'],recovery_identity=a.last_identity)
    raw=save_arrays(folder/'nonzero_rhs_witness.npz',trace=t,rhs=rhs,recovered=full,lifted=lifted)
    passed=max(v for e in errors for v in e.values())<=1e-10 and max(witness['recovery'],witness['original_operation'])<=1e-10
    result=dict(status='COMPLETED',pass_gate=passed,errors=errors,arrays=receipts,nonzero_rhs_witness=dict(witness,arrays=raw),
        hot_seconds=hot,hot_cache_bytes=a.hot_cache_bytes,actual_interior_port_cells=a.actual_interior_port_cells,
        calls=dict(a.calls),source=journal.source_state,timings=journal.timings,local_packet=p['local_packet'],
        global_fine_matrix_reads=0,global_fine_matrix_formations=0,global_fine_numeric_factors=0,new_complete_solves=0)
    write_json(folder/'hot_qualification.json',result)
    if not passed:raise ValueError('V71 exact hot original action gate')
    return result


def setup_service(role,journal):
    from .independent_tetra_study import load_boundary
    s=core.make_setup(scope.case_spec(role),scope.physical_for(role),journal)
    p=parent();b=load_boundary(s,p['boundary_arrays'],p['mode_sha256'],'q47')
    oracle=load_boundary(s,p['boundary_arrays'],p['mode_sha256'],'q63')
    a=service(journal,s,b,oracle)
    rhs=core.rhs_vector(s,b)
    if relative(rhs-a.arrays['full_rhs'],rhs)>1e-12:raise ValueError('V71 original packet/RHS identity')
    from .fixed_phase_fem import port_coordinate_scales
    from .dtn_port_3d import _mode_boundary_phase
    phase=np.array([_mode_boundary_phase(m,s['cfg']) for m in b['modes']])
    left,right=port_coordinate_scales(a.nt,a.H,phase)
    if not np.all(left[:a.nt]==1) or not np.all(right[:a.nt]==1):raise ValueError('fine FE coordinate scales')
    return s,b,oracle,a,rhs,left,right


def symbolic(A,journal,name):
    from .independent_tetra_study import petsc_matrix
    from .fullspace_v17_p3_oracle import _MumpsFactor
    matrix=petsc_matrix(A);f=None
    try:
        f=_MumpsFactor(matrix)
        with journal.measured('bounded_'+name+'_symbolic'):
            f.symbolic(matrix);info=f.info();controls=f.symbolic_memory_settings()
        estimate=max(int(info['infog'][str(k)]) for k in (16,17))
        if estimate<=0 or controls['icntl']['22']!=0:raise MemoryError('reliable in-core bounded symbolic required')
        return dict(info=info,controls=controls,estimate_mb=estimate,double_bytes=2*estimate*1_000_000,
                    rows=A.shape[0],nnz=A.nnz,ordering=f.preferred_ordering,numeric_calls=0)
    finally:
        if f is not None:f.destroy()
        matrix.destroy()


def pc_setup(folder,journal):
    scope.require_stage('PC_SETUP');s,b,oracle,a,rhs,left,right=setup_service('PC_SETUP',journal)
    with journal.measured('fixed_geometric_core_and_periodic_tet_halo'):
        patches,inventory=geometric_patches(s,a)
    arrays={f'{j}_{k}':v for j,p in enumerate(patches) for k,v in p.items()}
    owner=save_arrays(folder/'patch_owner_inventory.npz',**arrays)
    write_json(folder/'patch_inventory.json',dict(inventory,arrays=owner))
    # Original 960tet Z2 geometry; no coarse PDE, form, kernel, or teacher.
    import copy
    coarse_physical=copy.deepcopy(scope.plan_record()['physical_descriptor'])
    z=coarse_physical['geometry']['axes_nm']['z']
    coarse_physical['geometry']['axes_nm']['z']=[l+(r-l)*j/2 for l,r in zip(z[:-1],z[1:]) for j in range(2)]+[z[-1]]
    spec=dict(case='NOTCH',degree=2,h_ratio=1,cells=960,independent=6240,complete_modes=828,notch_tetrahedra=24)
    coarse=core.make_setup(spec,coarse_physical,journal)
    if coarse['P'].shape[1]+a.m>8192:raise MemoryError('fixed p2 coarse inventory cap')
    with journal.measured('true_p2_to_fine_trace_moment_interpolation'):
        Z,zi=coarse_trace_embedding(s,coarse,a,journal)
    parents=zi.pop('parent_cells');zreceipt=csr_save(folder/'sparse_Zgamma.npz',Z,parent_cells=parents)
    write_json(folder/'coarse_space_inventory.json',dict(zi,arrays=zreceipt,port_coordinate_commutes=True,ports=a.m))
    matrices=[];analysis=[]
    for j,p in enumerate(patches):
        with journal.measured('all_contributing_cells_patch_'+str(j)):
            A=local_principal(a,p['ids'])
            matrix=csr_save(folder/f'patch{j:02d}.npz',A)
        info=symbolic(A,journal,'patch'+str(j));analysis.append(info);matrices.append(matrix)
        write_json(folder/'patch_preparation_progress.json',dict(matrices=matrices,analysis=analysis,completed=j+1))
        del A;gc.collect()
    with journal.measured('local_and_complete_port_Galerkin_assembly'):
        E0=coarse_galerkin(a,Z,left,right)
    coarse_matrix=csr_save(folder/'coarse_E0.npz',E0);coarse_info=symbolic(E0,journal,'coarse')
    rng=np.random.default_rng(7103);galerkin=[]
    for j in range(2):
        w=rng.normal(size=E0.shape[0])+1j*rng.normal(size=E0.shape[0])
        v=prolong(Z,w)
        original=action_charge('P_Galerkin',lambda:left*a.apply_trace(right*v))
        pulled=restrict(Z,original);target=E0@w
        error=relative(pulled-target,target)
        dual=abs(np.vdot(v,original)-np.vdot(w,pulled))/max(np.linalg.norm(v)*np.linalg.norm(original),1e-30)
        rec=save_arrays(folder/f'Galerkin{j}.npz',w=w,Zw=v,original=original,pulled=pulled,coarse_action=target)
        galerkin.append(dict(operation=error,dual=dual,arrays=rec))
    total=sum(r['double_bytes'] for r in analysis)+coarse_info['double_bytes']
    admitted=total<=64*2**30
    math_pass=max(max(r['operation'],r['dual']) for r in galerkin)<=1e-10
    result=dict(status='COMPLETED' if admitted and math_pass else 'CAPACITY_BLOCKED' if not admitted else 'MATH_GATE_FAILED',
        pass_gate=admitted and math_pass,patch_inventory=inventory,patch_arrays=owner,matrices=matrices,analysis=analysis,
        coarse_matrix=coarse_matrix,coarse_symbolic=coarse_info,coarse_inventory=zi,Z=zreceipt,
        galerkin=galerkin,double_symbolic_sum_bytes=total,double_symbolic_sum_limit_bytes=64*2**30,
        symbolic_sum_admitted=admitted,local_numeric_count=0,coarse_numeric_count=0,global_fine_numeric_count=0,
        numeric_and_two_live_PC_witnesses='in ITERATE process before its sole KSP.solve; no factor serialization claim',
        hot_calls=dict(a.calls),source=journal.source_state,timings=journal.timings,local_packet=a.receipt)
    write_json(folder/'bounded_pc_preparation.json',result)
    if admitted and math_pass:
        # One fixed first patch supplies a paid local triangular calibration.
        # The complete pattern/symbolic sum is already frozen. This test
        # factor is destroyed and is explicitly rebuilt/charged in ITERATE.
        local,first=numeric_factors(dict(matrices=[],coarse_matrix=matrices[0],
            analysis=[],coarse_symbolic=analysis[0]),journal)
        rng=np.random.default_rng(7105);seconds=[]
        try:
            for j in range(2):
                v=rng.normal(size=analysis[0]['rows'])+1j*rng.normal(size=analysis[0]['rows'])
                began=time.perf_counter();z=BoundedTwoLevelPC.solve(first,v);seconds.append(time.perf_counter()-began)
                A=csr_load(matrices[0]);err=relative(A@z-v,v)
                if err>1e-8 or not np.isfinite(z).all():raise ValueError('fixed first patch local solve qualification')
                save_arrays(folder/f'local_forecast_witness{j}.npz',input=v,output=z,residual=A@z-v)
                del A
        finally:first.destroy()
        predicted_triangular=4*max(seconds)*total/max(analysis[0]['double_bytes'],1)
        result.update(local_numeric_count=1,local_forecast_calibration=dict(patch_index=0,
            triangular_seconds=seconds,triangular_calls=2,predicted_all_local_coarse_seconds=predicted_triangular,
            prediction='fourfold measured first-patch time scaled by double-symbolic byte sum; not a bound or measurement of all solves',
            factor_destroyed=True,will_be_rebuilt_and_charged_in_ITERATE=True))
        write_json(folder/'bounded_pc_preparation.json',result)
    return result


def numeric_factors(record,journal):
    from .independent_tetra_study import petsc_matrix
    from .fullspace_v17_p3_oracle import _MumpsFactor
    from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
    allreceipts=record['matrices']+[record['coarse_matrix']]
    infos=record['analysis']+[record['coarse_symbolic']];factors=[];remaining=sum(r['double_bytes'] for r in infos)
    try:
        for j,(receipt,expected) in enumerate(zip(allreceipts,infos,strict=True)):
            A=csr_load(receipt);matrix=petsc_matrix(A);f=_MumpsFactor(matrix)
            try:
                with journal.measured('bounded_pc_factor_symbolic_'+str(j)):
                    f.symbolic(matrix);info=f.info();estimate=max(int(info['infog'][str(k)]) for k in (16,17))
                if estimate!=expected['estimate_mb'] or f.symbolic_memory_settings()['icntl']['22']!=0:
                    raise ValueError('bounded factor frozen reliable symbolic identity')
                sample=process_tree_snapshot(int(os.environ['TASK042_WATCHDOG_PARENT_PID']),'V71-PC-numeric',include_pss=False)
                planned=sample['rss_bytes']+remaining+2*2**30
                admitted=sample['swap_bytes']==0 and planned<=96*2**30
                journal.event('bounded_local_or_coarse_numeric_admission',index=j,tree=sample,remaining_double_symbolic=remaining,
                              planned_simultaneous_bytes=planned,limit_bytes=96*2**30,admitted=admitted,global_fine_numeric=False)
                if not admitted:raise MemoryError("live + all remaining double symbolic + workspace PC cap")
                f.set_memory_limit_mb(2*estimate)
                with journal.measured('bounded_local_or_coarse_numeric_'+str(j)):f.numeric(matrix)
                factors.append(f);remaining-=2*estimate*1_000_000
            except BaseException:f.destroy();raise
            finally:matrix.destroy();del A;gc.collect()
        return factors[:-1],factors[-1]
    except BaseException:
        for f in factors:f.destroy()
        raise


def iterate(folder,journal,state):
    from petsc4py import PETSc
    from .physical_retained_fgmres import run_retained_fgmres
    from .tetra_coefficient_action import CoefficientFullAction
    from .independent_tetra_fields import complete_output
    scope.require_stage('ITERATE');record=scope.stage('PC_SETUP')
    s,b,oracle,a,full_rhs,left,right=setup_service('ITERATE',journal)
    reduced=a.condense_rhs(full_rhs);bhat=left*reduced
    rhs_receipt=save_arrays(folder/'physical_RHS.npz',full_rhs=full_rhs,reduced_rhs=reduced,bhat=bhat,left=left,right=right)
    Z=csr_load(record['Z']);pa=checked_arrays(record['patch_arrays'])
    patches=[{k:pa[f'{j}_{k}'] for k in ('ids','core')} for j in range(record['patch_inventory']['patches'])]
    action=lambda v:action_charge('I_scaled_trace',lambda:left*a.apply_trace(right*v))
    remaining=min(scope.window.snapshot()['heavy_remaining_seconds'],scope.window.case_remaining(active=True))
    hot=max(scope.stage('PREFLIGHT')['hot_seconds'])
    local_predicted=record['local_forecast_calibration']['predicted_all_local_coarse_seconds']
    forecast=min(21600.,256*(2*hot+local_predicted)+3600)
    write_json(folder/'pre_PC_numeric_forecast.json',dict(measured_hot_seconds=hot,
        paid_local_forecast=record['local_forecast_calibration'],iteration_prediction_seconds=forecast,
        PC_numeric_uncertainty_reserve_seconds=3600,output_reserve_seconds=4500,remaining_seconds=remaining,
        admitted=remaining>=forecast+3600+4500))
    if remaining<forecast+3600+4500:raise RuntimeError('local/coarse numeric, iteration and full-output time admission')
    local,coarse=numeric_factors(record,journal);pc=BoundedTwoLevelPC(Z,patches,local,coarse,action)
    independent=CoefficientFullAction(s,oracle,15);evaluations=[];counter=0

    def evaluate(target,residual):
        nonlocal counter
        t=right*target.array;full=a.recover(t,full_rhs)
        aud,res,original_rhs=action_charge('I_public_original',lambda:independent.audit(full,full_rhs,journal))
        operation=a.last_identity['maximum_cell_operation_scaled']
        defect=a.lift_residual(residual.array/left)-res
        scale=a.identity_operation_scale(t,full,original_rhs)
        identity=float(np.linalg.norm(defect)/max(scale,1e-300))
        aud.update(recovery_identity=operation,Schur_original_identity=identity,
            Schur_original_identity_absolute=float(np.linalg.norm(defect)),Schur_original_operation_scale=scale,
            Schur_original_difference_RHS_scaled=relative(defect,original_rhs))
        raw=save_arrays(folder/f'original_snapshot_{counter:02d}.npz',trace=t,full=full,rhs=original_rhs,residual=res)
        counter+=1;evaluations.append(dict(audit=aud,arrays=raw));write_json(folder/'original_monitor_progress.json',dict(rows=evaluations))
        return aud

    # Two actual fixed PC calls. They are numerical interface tests, not
    # reference-driven choices and not a convergence requirement.
    rng=np.random.default_rng(7104);pc_rows=[]
    try:
        v=rng.normal(size=len(bhat))+1j*rng.normal(size=len(bhat));alpha=.3+.7j;first_output=None
        for j in range(2):
            input_vector=v if j==0 else alpha*v;began=time.perf_counter();z=pc(input_vector)
            error=0. if j==0 else relative(z-alpha*first_output,alpha*first_output)
            if j==0:first_output=z.copy()
            pc_rows.append(dict(seconds=time.perf_counter()-began,arrays=save_arrays(folder/f'PC{j}.npz',input=input_vector,output=z),finite=bool(np.isfinite(z).all()),complex_linearity=error))
        PCpass=all(r['finite'] and r['complex_linearity']<=1e-10 for r in pc_rows)
        write_json(folder/'live_PC_qualification.json',dict(pass_gate=PCpass,rows=pc_rows,calls=pc.calls,
            linear_operator_frozen=True,reference_reads=0))
        if not PCpass:raise ValueError('fixed live PC finite/complex linearity')
        remaining=min(scope.window.snapshot()['heavy_remaining_seconds'],scope.window.case_remaining(active=True))
        step_forecast=max(scope.stage('PREFLIGHT')['hot_seconds'])+max(r['seconds'] for r in pc_rows)
        forecast=min(21600.,256*step_forecast+3600)
        write_json(folder/'iteration_forecast.json',dict(step_upper_seconds=step_forecast,iteration_upper_seconds=forecast,
            output_reserve_seconds=4500,remaining_seconds=remaining,admitted=remaining>=forecast+4500))
        if remaining<forecast+4500:raise RuntimeError('complete iteration plus original/output reserve')
        start=time.monotonic();rhs=PETSc.Vec().createSeq(len(bhat),comm=PETSc.COMM_SELF);rhs.array[:]=bhat
        def save(iteration,vector):
            rec=save_arrays(folder/f'retained_{iteration:04d}.npz',scaled_retained=vector.array.copy(),trace=right*vector.array)
            write_json(folder/'latest_retained.json',dict(iteration=iteration,arrays=rec,RHS=rhs_receipt,local_packet=a.receipt,source=state))
        def append(name,row):
            with (folder/name).open('a') as f:f.write(json.dumps(row,allow_nan=False)+'\n');f.flush()
        def vector_action(v):
            out=v.duplicate();out.array[:]=action(v.array);return out
        def vector_pc(v):
            out=v.duplicate();out.array[:]=pc(v.array);return out
        policy=dict(original_key='true',physical_limits=dict(true=1e-6,native=1e-6,augmented=1e-6,port=1e-6),
            identity_limits=dict(MPC_identity=1e-10,rhs_q47_q63=1e-10,recovery_identity=1e-10,Schur_original_identity=1e-10))
        try:
            result=run_retained_fgmres(rhs,vector_action,vector_pc,evaluate=evaluate,
                checkpoint=lambda iteration,vec,row:write_json(folder/'latest_original_gate.json',row),append=append,
                seconds=lambda:time.monotonic()-start,save_retained=save,restart=32,max_it=256,residual_interval=32,
                candidate_rtol=1e-11,retained_tolerance=1e-11,evaluation_policy=policy,
                resource_sample=scope.window.require_live,
                stop_requested=lambda:time.monotonic()-start>=21600 or scope.window.snapshot()['heavy_remaining_seconds']<=4500
                    or scope.window.case_remaining(active=True)<=4500)
            final=result.pop('final_solution');t=right*final.array.copy();final.destroy()
            returned=save_arrays(folder/'retained_returned.npz',trace_port=t,rhs=reduced,scaled_rhs=bhat,left=left,right=right)
            pending=dict(status='RECOVERY_PENDING',retained_returned=returned,RHS=rhs_receipt,local_packet=a.receipt,
                source=state,spec=s['spec'],physical=s['physical'],boundary_arrays=parent()['boundary_arrays'],mode_sha256=b['digest'],iteration=result)
            write_json(folder/'retained_audit_pending.json',pending)
            write_json(scope.window.TMP/'scientific_queue_frozen.json',dict(retained=returned,source=state['source_sha'],no_more_solves=True))
        finally:rhs.destroy()
    finally:
        before=journal.event('all_local_coarse_factors_before_release')['RSS_bytes'];pc_calls=dict(pc.calls);pc_seconds=dict(pc.seconds)
        pc.destroy();pc=None;gc.collect()
        after=journal.event('all_local_coarse_factors_released')['RSS_bytes']
        write_json(folder/'factor_release_lifecycle.json',dict(before_RSS_bytes=before,after_RSS_bytes=after,RSS_decreased=after<before,
            global_fine_factor_count=0,local_numeric_count=len(patches),coarse_numeric_count=1))
    with journal.measured('final_full_original_recovery_after_KSP_and_PC_release'):x=a.recover(t,full_rhs)
    arrays=save_arrays(folder/'solution.npz',x=x,u_independent=x[:a.n],u_native=s['P']@x[:a.n],port=x[a.n:],rhs=full_rhs,
        kappa=s['kappa'],masters=s['masters'],slaves=s['floquet'].mpc.slaves,P_data=s['P'].data,P_indices=s['P'].indices,P_indptr=s['P'].indptr,**s['geometry'])
    aud,res,orrhs=action_charge('I_final_public_original',lambda:independent.audit(x,full_rhs,journal))
    aud['arrays']=save_arrays(folder/'independent_original.npz',residual=res,rhs=orrhs,action=orrhs-res,x=x)
    pending.update(status='AUDIT_PENDING',arrays=arrays,audit=aud,equation_pass=aud['pass_gate'],internal_recovery_identity=a.last_identity,
        new_complete_solves=1,new_numeric_factors=len(patches)+1,global_fine_numeric_factors=0,pc_calls=pc_calls,pc_seconds=pc_seconds)
    write_json(folder/'returned_audit_pending.json',pending)
    a.release_hot();a=independent=Z=local=coarse=None;gc.collect();journal.event('unneeded_exact_operator_cache_released_before_fields')
    output,accuracy=complete_output(s,b,x,folder,journal)
    output['official']=bool(aud['pass_gate']);output['classification']='OFFICIAL_EQUATION_QUALIFIED' if aud['pass_gate'] else 'DIAGNOSTIC_ONLY_EQUATION_FAIL'
    write_json(folder/'field_output_classification.json',dict(official=output['official'],classification=output['classification']))
    result=dict(pending,status='COMPLETED',output=output,accuracy=accuracy,deployment_complete=True,
        pipeline_complete=True,scientific_solve_pass=aud['pass_gate'] and pending['iteration']['final_evaluation']['solve_gate_pass'],
        source=state,timings=journal.timings,calls=journal.calls,prepared_start=True,global_fine_K_reads=0,global_fine_S_reads=0)
    write_json(folder/'complete_scientific_result.json',result);return result


def execute(role,folder,state):
    budget=scope.memory_budget(role)
    if state.get('memory_budget')!=budget:raise ValueError('V71 resolved/live memory contract')
    journal=Journal(folder,window_scope=scope.window,planning_limit_bytes=budget['planning_gib']*2**30);journal.source_state=state
    if role=='PREFLIGHT':return preflight(folder,journal)
    if role=='PC_SETUP':return pc_setup(folder,journal)
    if role=='ITERATE':return iterate(folder,journal,state)
    if role=='VERIFY_COST':
        from benchmarks.collect_bounded_trace import verify
        return verify(folder,journal)
    raise ValueError('V71 explicit one-run role')
