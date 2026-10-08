"""Thin staged V65 consumer of the qualified full tetra Maxwell pipeline."""
import gc
import hashlib
import json
import time
from pathlib import Path
import numpy as np
from src.runners.task042_shared import write_json
from . import p6_completion_scope as scope
from . import independent_tetra_reference as core
from .scattering_anchor import Journal,relative,save_arrays,array_hash
from .scattering_anchor_checks import checked_arrays
from .tetra_coefficient_action import CoefficientBodyAction,CoefficientFullAction
from .tetra_body_checkpoint import save_checkpoint,load_checkpoint


def setup_identity(s):
    s['mesh'].topology.create_entity_permutations()
    b=s['V'].element.basix_element
    arrays=dict(**s['geometry'],P_data=s['P'].data,P_indices=s['P'].indices,P_indptr=s['P'].indptr,
        masters=s['masters'],slaves=s['floquet'].mpc.slaves,
        cell_permutations=s['mesh'].topology.get_cell_permutation_info(),
        basis_coefficients=b.coefficient_matrix)
    return dict(physical=s['physical'],degree=s['spec']['degree'],local_dim=s['V'].element.space_dimension,
        superdegree=b.embedded_superdegree,basis_entity_dofs=b.entity_dofs,basis_map=str(b.map_type),
        dtype='complex128',integer_dtype='int64',kappa=s['kappa'].tolist(),k0=s['cfg'].k0,body_q=15,
        arrays={k:array_hash(np.asarray(v)) for k,v in arrays.items()}),arrays


def readonly_boundaries(s,journal):
    from .independent_tetra_study import load_boundary
    p=scope.plan_record()['prior_boundary'];r=p['parent_record']
    if hashlib.sha256((scope.ROOT/r['path']).read_bytes()).hexdigest()!=r['sha256']:raise ValueError('V64 boundary parent record hash')
    # Bind the actual, unrounded parent mesh as well as the new basis/MPC.
    from . import local_h_pilot_scope as prior
    old=checked_arrays(prior.stage('PREFLIGHT')['marking']['arrays'])
    for k in ('geometry_x','geometry_dofmap'):
        if not np.array_equal(old[k],s['geometry'][k]):raise ValueError('V64 boundary actual geometric identity')
    if s['V'].element.space_dimension!=216 or s['P'].shape!=(1005528,980352):raise ValueError('saved p6 boundary basis/MPC inventory')
    with journal.measured('checked_readonly_V64_q47_q63'):
        first=load_boundary(s,p['arrays'],p['mode_sha256'],'q47')
        second=load_boundary(s,p['arrays'],p['mode_sha256'],'q63')
    return first,second


def basis_first_cell(ev,c,coefficients,cfg,epsilon,kappa):
    """Original transformed-test/trial tables, restricted to one small cell."""
    J,_,det=ev.geometry[c];T=ev.transform(c)
    basis=np.einsum('ij,qjc->qic',T,ev.values)@np.linalg.inv(J)
    ck=np.einsum('ij,qjc->qic',T,ev.curls)@J.T/det+1j*np.cross(kappa,basis)
    value=np.einsum('qjc,j->qc',basis,coefficients)
    curl=np.einsum('qjc,j->qc',ck,coefficients)
    local=abs(det)*(np.einsum('q,qjc,qc->j',ev.weights,ck.conj(),curl/cfg.mu_r)
        -cfg.k0**2*epsilon*np.einsum('q,qjc,qc->j',ev.weights,basis.conj(),value))
    return local


def fixed_cells(s,ev):
    """A priori round-robin materials/directions, alternating geometric ends."""
    groups={}
    for c,t in enumerate(s['geometry']['cell_tags']):
        groups.setdefault((int(t),int(ev.permutations[c])),[]).append(c)
    bytag={}
    for (tag,perm),ids in sorted(groups.items()):
        ids.sort(key=lambda c:tuple(s['geometry']['cell_centers'][c]))
        bytag.setdefault(tag,[]).append((perm,ids))
    selected=[];tags=sorted(bytag);i=0
    while len(selected)<24 and any(i<len(bytag[t]) for t in tags):
        for tag in tags:
            if i>=len(bytag[tag]):continue
            _,ids=bytag[tag][i];c=ids[0 if i%2==0 else -1]
            if c not in selected:selected.append(c)
            if len(selected)==24:break
        i+=1
    if len(selected)<24:
        ordering=sorted(range(len(ev.geometry)),key=lambda c:tuple(s['geometry']['cell_centers'][c]))
        for c in ordering[::max(1,len(ordering)//24)]:
            if c not in selected:selected.append(c)
            if len(selected)==24:break
    return np.asarray(selected,np.int32)


def preflight(folder,journal):
    s=core.make_setup(scope.case_spec('PREFLIGHT'),scope.physical_for('PREFLIGHT'),journal)
    kernel=CoefficientBodyAction(s,17);ids=fixed_cells(s,kernel.ev)
    # Persist selection before observing numerical differences.
    frozen=save_arrays(folder/'frozen_cell_selection.npz',cells=ids,permutations=kernel.ev.permutations[ids],
        tags=s['geometry']['cell_tags'][ids],centers=s['geometry']['cell_centers'][ids],
        Jacobians=np.asarray([kernel.ev.geometry[int(c)][0] for c in ids]))
    errors=[];rng=np.random.default_rng(6507);old_seconds=0.;new_seconds=0.
    with journal.measured('maximum24_actual_p6_local_pairs'):
        for c in ids:
            c=int(c);coef=rng.normal(size=216)+1j*rng.normal(size=216)
            t=time.perf_counter();old=basis_first_cell(kernel.ev,c,coef,s['cfg'],kernel.materials[int(s['geometry']['cell_tags'][c])],s['kappa']);old_seconds+=time.perf_counter()-t
            t=time.perf_counter();new=kernel.cell(c,coef);new_seconds+=time.perf_counter()-t
            d=new-old
            errors.append(dict(cell=c,relative=relative(d,old),absolute=float(np.linalg.norm(d)),reference_norm=float(np.linalg.norm(old)),
                operation_scaled=float(np.linalg.norm(d)/max(np.linalg.norm(new)+np.linalg.norm(old),1e-300))))
            write_json(folder/'cell_pair_progress.json',errors)
    identity,_=setup_identity(s);cap=core.assembly_capacity(s,journal)
    del kernel,s;gc.collect()
    # One saved complete p5 original-action vector, no p5 solve or field replay.
    from . import fine_tetra_scope as parent
    from .independent_tetra_study import load_boundary
    b=parent.stage('B');saved=checked_arrays(b['audit']['arrays']);coef=checked_arrays(b['arrays'])
    s=core.make_setup(b['spec'],b['physical'],journal)
    oracle=load_boundary(s,b['boundary_arrays'],b['mode_sha256'],'q63')
    action=CoefficientFullAction(s,oracle,15)
    with journal.measured('one_saved_p5_original_vector_consumption'):
        actual=action(saved['x']);journal.calls['A']+=1
    delta=actual-saved['action'];error=relative(delta,saved['action'])
    witness=save_arrays(folder/'saved_p5_original_pair.npz',input=saved['x'],original=saved['action'],coefficient_first=actual,
        delta=delta,physical_rhs=saved['rhs'])
    if not np.array_equal(coef['x'],saved['x']):raise ValueError('saved p5 original vector is not the returned coefficients')
    result=dict(status='COMPLETED',pass_gate=max(r['relative'] for r in errors)<=1e-10 and error<=1e-10,
        fixed_p6_cells=frozen,cell_pairs=errors,p6_identity=identity,P6_capacity=cap,
        local_timing=dict(old_transformed_tables_seconds=old_seconds,coefficient_first_seconds=new_seconds,
            single_small_pairing_only=True,whole_case_speedup='NOT_MEASURED'),
        saved_p5=dict(relative=error,absolute=float(np.linalg.norm(delta)),operation_scaled=float(np.linalg.norm(delta)/max(np.linalg.norm(actual)+np.linalg.norm(saved['action']),1e-300)),
            arrays=witness,parent_original=b['audit']['arrays'],parent_solution=b['arrays'],consumption=action.body.last),
        new_numeric_factors=0,new_complete_solves=0,new_full_body_actions=1,new_p6_cell_pairs=len(ids),source=journal.source_state,timings=journal.timings)
    write_json(folder/'oracle_qualification.json',result);return result


def prepare(folder,journal):
    scope.require_stage('PREPARE')
    s=core.make_setup(scope.case_spec('PREPARE'),scope.physical_for('PREPARE'),journal)
    identity,arrays=setup_identity(s)
    if identity!=scope.stage('PREFLIGHT')['p6_identity']:raise ValueError('P6 actual identity changed after oracle qualification')
    cap=core.assembly_capacity(s,journal)
    if not cap['admitted']:return dict(status='CAPACITY_BLOCKED',capacity=cap)
    b,oracle=readonly_boundaries(s,journal)
    checkpoint_pointer=scope.ARTIFACT/'body_checkpoint.json'
    if checkpoint_pointer.exists():
        receipt=json.loads(checkpoint_pointer.read_text())
        with journal.measured('reload_committed_body_CSR'):
            K,manifest,_=load_checkpoint(receipt,identity)
        return dict(status='COMPLETED',checkpoint=receipt,capacity=cap,form=manifest['form'],
            new_body_builds=0,new_numeric_factors=0,new_complete_solves=0,prepared_resume=True,source=journal.source_state,timings=journal.timings)
    marker=scope.window.TMP/'body_build_started.json'
    if marker.exists():raise RuntimeError('body build already attempted; diagnose incomplete checkpoint without blind rebuild')
    write_json(marker,dict(source=journal.source_state,identity=identity,clock=scope.window.snapshot(),maximum_body_builds=1))
    K,form=core.production_body(s,journal)
    with journal.measured('atomic_unscaled_body_CSR_checkpoint_IO'):
        receipt=save_checkpoint(scope.ARTIFACT/'body_K',K,identity,arrays,form=form,source=journal.source_state,
            boundary=dict(q47=b['arrays'],q63=oracle['arrays'],mode_sha256=b['digest']))
        write_json(checkpoint_pointer,receipt)
    result=dict(status='COMPLETED',checkpoint=receipt,capacity=cap,form=form,body_nnz=K.nnz,
        new_body_builds=1,new_numeric_factors=0,new_complete_solves=0,prepared_resume=False,
        boundary_arrays={'q47':b['arrays'],'q63':oracle['arrays']},mode_sha256=b['digest'],
        scientific_status='ASSEMBLED_NOT_YET_ORACLE_VERIFIED',source=journal.source_state,timings=journal.timings)
    write_json(folder/'prepared_result.json',result);return result


def prepared_provider(s,folder,journal):
    receipt=scope.stage('PREPARE')['checkpoint'];identity,_=setup_identity(s)
    with journal.measured('readonly_body_K_checkpoint_identity_and_reopen'):
        K,manifest,arrays=load_checkpoint(receipt,identity)
    b,oracle=readonly_boundaries(s,journal)
    return dict(K=K,form=manifest['form'],boundary=b,oracle=oracle,checkpoint=receipt,owners=arrays)


def execute(role,folder,state):
    budget=scope.memory_budget(role)
    if state.get('memory_budget')!=budget:raise ValueError('V65 resolved/live scope memory')
    journal=Journal(folder,window_scope=scope.window,planning_limit_bytes=budget['planning_gib']*2**30);journal.source_state=state
    if role=='PREFLIGHT':return preflight(folder,journal)
    if role=='PREPARE':return prepare(folder,journal)
    if role=='SOLVE_COMPLETE':
        from .independent_tetra_study import solve
        return solve(role,folder,journal,state,scope_module=scope,prepared_provider=prepared_provider,
            action_factory=lambda s,b:CoefficientFullAction(s,b,17))
    if role=='VERIFY_COST':
        from benchmarks.collect_p6_completion import verify
        return verify(folder,journal)
    raise ValueError('V65 explicit stage inventory')
