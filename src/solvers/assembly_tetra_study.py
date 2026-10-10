"""Thin V70 queue using the common tetra solve/recovery/output tail."""
import gc
import json
from pathlib import Path

import numpy as np
from src.runners.task042_shared import write_json
from . import assembly_tetra_scope as scope
from . import independent_tetra_reference as core
from .scattering_anchor import Journal,relative,save_arrays
from .tetra_body_checkpoint import file_digest
from .p6_completion_study import setup_identity
from .tetra_cell_kernel import TetraCellKernel
from .tetra_coefficient_action import CoefficientBodyAction,CoefficientFullAction
from .tetra_assembly_packet import partition,build,RetainedPacket,LocalTracePacket
from .scattering_anchor_checks import checked_arrays


def packet_identity(s,b,oracle):
    identity,_=setup_identity(s)
    return dict(full_identity=identity,mode_sha256=b['digest'],boundary_arrays=b['arrays'],oracle_arrays=oracle['arrays'],
                partition='actual_Basix_entity3_native_to_compact_MPC_unique_owner',kernel='packed_DG0_affine_tetra_Ckappa_q13')


def setup(role,journal):return core.make_setup(scope.case_spec(role),scope.physical_for(role),journal)


def preflight(folder,journal):
    s=setup('PREFLIGHT',journal);internal,retained,_,_,_=partition(s)
    centers=s['geometry']['cell_centers'];tags=s['data'].cell_tags.values
    candidates=[]
    for tag in sorted(np.unique(tags)):
        ids=np.flatnonzero(tags==tag);ordered=sorted(ids,key=lambda c:tuple(centers[c]))
        candidates.extend([int(ordered[0]),int(ordered[-1])])
    candidates.extend([int(np.argmin(centers[:,0])),int(np.argmax(centers[:,1]))])
    chosen=list(dict.fromkeys(candidates))[:8]
    write_json(folder/'cell_preregistration.json',dict(cells=chosen,rule='lexicographic first/last of each actual material then periodic x/y extremes',maximum=8))
    kernel=TetraCellKernel(s,journal);oracle=CoefficientBodyAction(s,15);rng=np.random.default_rng(7001);rows=[]
    with journal.measured('at_most_eight_actual_cell_kernel_Basix_and_translation_pairs'):
        for c in chosen:
            raw=kernel.tensor(c);shift=kernel.tensor(c,translated=True)
            v=rng.normal(size=(140,2))+1j*rng.normal(size=(140,2));actual=oracle.cell(c,v)
            errors=[relative(raw@v[:,j]-actual[:,j],actual[:,j]) for j in range(2)]
            translation=relative(raw-shift,raw)
            rows.append(dict(cell=c,tag=int(tags[c]),permutation=int(kernel.permutations[c]),unrounded_key=kernel.key(c),
                two_action_errors=errors,translation_tensor_relative=translation))
            if max(*errors,translation)>1e-10:raise ValueError('actual packed cell/Piola/direction/translation gate')
    arrays=save_arrays(folder/'actual_partition.npz',interior=internal,retained=retained,masters=s['masters'])
    result=dict(status='COMPLETED',pass_gate=True,kernel=kernel.identity,cell_pairs=rows,partition=arrays,
        independent=1943745,internal=int(internal.size),retained=len(retained),new_numeric_factors=0,new_complete_solves=0,
        actual_local_kernel_calls=kernel.calls,source=journal.source_state,timings=journal.timings,
        production_full_K_reads=0,production_full_K_formed=0)
    write_json(folder/'cell_kernel_qualification.json',result);return result


def fixed_inputs(service):
    rng=np.random.default_rng(7007)
    values=rng.normal(size=(len(service.retained),2))+1j*rng.normal(size=(len(service.retained),2))
    values[-service.m:]/=np.maximum(np.abs(service.H[:,None]),1.)
    return values


def prepare(folder,journal,state):
    scope.require_stage('BUILD');s=setup('BUILD',journal)
    b=core.boundary(s,47,journal,folder);oracle=core.boundary(s,63,journal,folder)
    from .scattering_accuracy_boundary import carrier_pair
    pair=carrier_pair(b['carrier'],oracle['carrier'],b['identities'],expected_modes=828)
    inc=relative(b['incident']-oracle['incident'],oracle['incident'])
    if not pair['pass'] or inc>1e-11:raise ValueError('new complete828 q47/q63 gate')
    write_json(folder/'boundary_pair.json',dict(pair=pair,incident=inc))
    rhs=core.rhs_vector(s,b);kernel=TetraCellKernel(s,journal)
    with journal.measured('assembly_time_cell_formed_S_and_packet'):
        local,matrix=build(s,b,rhs,kernel,folder,journal,identity=packet_identity(s,b,oracle),source=state)
    service=RetainedPacket(local,matrix);inputs=fixed_inputs(service)
    outputs=np.column_stack([service.matrix@inputs[:,j] for j in range(2)])
    action_arrays=save_arrays(folder/'retained_action_witness.npz',inputs=inputs,outputs=outputs,retained=service.retained)
    # Independent body+q63 acts on fully recovered vectors, including a fixed
    # nonzero interior and port RHS. This is never an initial iterate.
    witness_rhs=rhs.copy();witness_rhs[:service.n]+=np.sin(np.arange(service.n)*.173)*1e-3
    witness_rhs[service.n:]+=1e-3*(np.sin(np.arange(service.m)) + 1j*np.cos(np.arange(service.m)))
    with journal.measured('local_packet_two_arbitrary_RHS_recoveries'):
        full=np.column_stack([service.recover(inputs[:,j],witness_rhs) for j in range(2)])
        condensed=np.column_stack([service.lift_residual(service.condense_rhs(witness_rhs)-outputs[:,j]) for j in range(2)])
    with journal.measured('two_complete_recovered_PUBLIC_BASIX_original_actions'):
        original=CoefficientFullAction(s,oracle,15)(full);journal.calls['A']+=2
    residual=witness_rhs[:,None]-original;difference=residual-condensed
    errors=[]
    for j in range(2):
        total=relative(difference[:,j],original[:,j]);body=relative(difference[:service.n,j],original[:service.n,j])
        D=service.DT.T;portscale=np.abs(D@full[:service.n,j])+np.abs(service.H*full[service.n:,j])+np.abs(witness_rhs[service.n:])
        port=relative(difference[service.n:,j],portscale)
        errors.append(dict(total=total,body=body,port_operation=port))
    raw=save_arrays(folder/'recovered_original_witness.npz',retained=inputs,full=full,rhs=witness_rhs,
        original_action=original,original_residual=residual,condensed_residual_lift=condensed)
    maximum=max(v for e in errors for v in e.values())
    qualification=dict(pass_gate=maximum<=1e-10,errors=errors,arrays=raw,source=state,
        complete_nonzero_internal_and_port_rhs=True,independent='PUBLIC_BASIX_Q15_TRIANGLE63',recovery=service.last_identity)
    write_json(folder/'reduction_qualification.json',qualification)
    counters={k:service.manifest[k] for k in ('full_body_assemble_matrix','full_K_reads','full_A_materializations','old_recovery_reads')}
    result=dict(status='COMPLETED',pass_gate=qualification['pass_gate'],local_packet=local,checkpoint=matrix,
        qualification=qualification,retained_action_witness=action_arrays,boundary_arrays={'q47':b['arrays'],'q63':oracle['arrays']},
        mode_sha256=b['digest'],actual_full_rows=service.full_rows,actual_retained_rows=len(service.retained),nnz=service.matrix.nnz,
        bytes=local['bytes']+matrix['bytes'],local_LU_count=service.manifest['local_LU_count'],producer_counters=counters,
        capacity=dict(admitted=True,actual_retained_rows=len(service.retained),graph=service.matrix_receipt,
                      planning_gib=256,allocation_gate='Journal actual preallocation and live RSS',full_K=False),
        form=kernel.identity,source=state,timings=journal.timings,new_numeric_factors=0,new_complete_solves=0)
    write_json(folder/'assembly_time_qualification.json',result)
    if not result['pass_gate']:raise ValueError('new complete original reduction gate')
    return result


def action(folder,journal):
    scope.require_stage('ACTION');record=scope.stage('BUILD')
    with journal.measured('cold_local_packet_boundary_read_no_global_S'):
        service=LocalTracePacket(record['local_packet'])
    reference=checked_arrays(record['retained_action_witness']);errors=[];receipts=[]
    for j in range(2):
        with journal.measured('first_local_trace_action' if j==0 else 'second_local_trace_action'):
            out=service.apply_trace(reference['inputs'][:,j])
        target=reference['outputs'][:,j]
        errors.append(dict(full=relative(out-target,target),FE=relative(out[:service.nt]-target[:service.nt],target[:service.nt]),
                           port=relative(out[service.nt:]-target[service.nt:],target[service.nt:])))
        receipts.append(save_arrays(folder/f'action{j}.npz',input=reference['inputs'][:,j],output=out,reference=target))
        write_json(folder/f'action{j}.json',dict(errors=errors[-1],arrays=receipts[-1],calls=dict(service.calls)))
    result=dict(status='COMPLETED',pass_gate=max(v for e in errors for v in e.values())<=1e-10,errors=errors,
        arrays=receipts,local_packet=record['local_packet'],calls=service.calls,exact_cache_peak_bytes=service.live_cache_bytes,
        new_numeric_factors=0,new_complete_solves=0,timings=journal.timings,source=journal.source_state)
    if any(result['calls'][k] for k in ('global_K_reads','global_S_reads','global_FE_matrix_formations','factors')):raise ValueError('local-only ACTION consumption')
    write_json(folder/'local_action_qualification.json',result);return result


def retained_provider(s,folder,journal):
    from .independent_tetra_study import load_boundary
    record=scope.stage('BUILD');b=load_boundary(s,record['boundary_arrays'],record['mode_sha256'],'q47')
    oracle=load_boundary(s,record['boundary_arrays'],record['mode_sha256'],'q63')
    with journal.measured('own_unscaled_S_and_local_packet_checked_reopen'):
        service=RetainedPacket(record['local_packet'],record['checkpoint'],identity=packet_identity(s,b,oracle))
    rhs=core.rhs_vector(s,b)
    if relative(rhs-service.arrays['full_rhs'],rhs)>1e-12:raise ValueError('new packet original physical RHS')
    # The sealed physical reduced RHS has already been independently verified.
    return dict(recovery=service,boundary=b,oracle=oracle,full_rhs=rhs,rhs=service.matrix_arrays['rhs'],
        qualification=record['qualification'],capacity=record['capacity'],form=record['form'],producer_counters=record['producer_counters'])


def execute(role,folder,state):
    budget=scope.memory_budget(role)
    if state.get('memory_budget')!=budget:raise ValueError('V70 resolved/live memory mismatch')
    journal=Journal(folder,window_scope=scope.window,planning_limit_bytes=budget['planning_gib']*2**30);journal.source_state=state
    if role=='PREFLIGHT':return preflight(folder,journal)
    if role=='BUILD':return prepare(folder,journal,state)
    if role=='ACTION':return action(folder,journal)
    if role=='SOLVE':
        from .independent_tetra_study import solve
        return solve(role,folder,journal,state,scope_module=scope,retained_provider=retained_provider,
                     action_factory=lambda s,b:CoefficientFullAction(s,b,15))
    if role=='VERIFY_COST':
        from benchmarks.collect_assembly_tetra import verify
        return verify(folder,journal)
    raise ValueError('V70 explicit one-run calculation')
