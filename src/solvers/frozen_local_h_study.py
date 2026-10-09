"""Thin V66 mesh consumer, staged preparation and existing complete solve."""
import gc
import hashlib
import json
import numpy as np
from src.runners.task042_shared import write_json
from . import frozen_local_h_scope as scope
from . import independent_tetra_reference as core
from .p6_completion_study import setup_identity,prepare as prepare_body
from .scattering_anchor import Journal,save_arrays,relative
from .scattering_anchor_checks import checked_arrays
from .tetra_body_checkpoint import load_checkpoint,body_fingerprint
from .tetra_coefficient_action import CoefficientFullAction


def preflight(folder,journal):
    # Only one old p4 vector is consumed; no old solve or full field replay.
    from . import fine_tetra_scope as parent
    from .independent_tetra_study import load_boundary
    old=parent.stage('A');v=checked_arrays(old['audit']['arrays'])
    s=core.make_setup(old['spec'],old['physical'],journal)
    b=load_boundary(s,old['boundary_arrays'],old['mode_sha256'],'q63')
    action=CoefficientFullAction(s,b,13)
    with journal.measured('one_saved_p4_original_vector_consumption'):
        actual=action(v['x']);journal.calls['A']+=1
    error=relative(actual-v['action'],v['action'])
    receipt=save_arrays(folder/'saved_p4_action_pair.npz',x=v['x'],original=v['action'],coefficient_first=actual,delta=actual-v['action'])
    consumption=action.body.last
    del s,b,action,v,actual;gc.collect()
    # Exact frozen mesh only: never calls a marking or refinement routine.
    s=core.make_setup(scope.case_spec('PREFLIGHT'),scope.physical_for('PREFLIGHT'),journal)
    identity,arrays=setup_identity(s);cap=core.assembly_capacity(s,journal)
    rng=np.random.default_rng(6601);P=s['P']
    x=rng.normal(size=P.shape[1])+1j*rng.normal(size=P.shape[1]);y=rng.normal(size=P.shape[0])+1j*rng.normal(size=P.shape[0])
    px=P@x;dual=abs(np.vdot(px,y)-np.vdot(x,P.conj().T@y))/max(np.linalg.norm(px)*np.linalg.norm(y),1e-300)
    b=s['V'].element.basix_element
    if (b.dim,b.embedded_superdegree)!=(84,4):raise ValueError('V66 actual p4 basis/superdegree')
    stored=save_arrays(folder/'actual_frozen_mesh_identity.npz',**arrays)
    result=dict(status='COMPLETED',pass_gate=error<=1e-10 and dual<=1e-12 and cap['admitted'],
        body_identity=identity,frozen_mesh_arrays=stored,original_mesh=scope.case_spec('PREFLIGHT')['mesh_override'],
        capacity=cap,complex_dual=dual,production_body_q=11,independent_body_q=13,
        actual=dict(cells=len(s['geometry']['geometry_dofmap']),native=P.shape[0],independent=P.shape[1],
            rows=P.shape[1]+828,degree=4,local_dim=b.dim,superdegree=b.embedded_superdegree,
            notch_tetrahedra=int(np.count_nonzero((s['geometry']['regular_tags']==s['cfg'].tags.grating)&(s['geometry']['cell_tags']==s['cfg'].tags.air)))),
        saved_p4=dict(relative=error,arrays=receipt,parent=old['audit']['arrays'],consumption=consumption),
        new_body_builds=0,new_numeric_factors=0,new_complete_solves=0,new_full_body_actions=1,
        source=journal.source_state,timings=journal.timings)
    write_json(folder/'preflight_qualification.json',result);return result


def fresh_boundaries(s,folder,journal):
    b=core.boundary(s,47,journal,folder);o=core.boundary(s,63,journal,folder)
    return b,o


def prepared_provider(s,folder,journal):
    from .independent_tetra_study import load_boundary
    p=scope.stage('PREPARE');identity,_=setup_identity(s)
    changed=s['spec']['complete_modes']==1188
    with journal.measured('readonly_body_K_identity_and_reopen'):
        K,m,arrays=load_checkpoint(p['checkpoint'],identity,allow_mode_change=changed)
    if changed:
        b,o=fresh_boundaries(s,folder,journal)
        journal.event('same_body_new_complete_modes',producer_body_fingerprint=body_fingerprint(m['identity']),
            consumer_body_fingerprint=body_fingerprint(identity),new_boundary_modes=1188,old_boundary_not_used=True)
    else:
        with journal.measured('checked_readonly_this_case_q47_q63'):
            b=load_boundary(s,p['boundary_arrays'],p['mode_sha256'],'q47')
            o=load_boundary(s,p['boundary_arrays'],p['mode_sha256'],'q63')
    return dict(K=K,form=m['form'],boundary=b,oracle=o,owners=arrays,checkpoint=p['checkpoint'])


def execute(role,folder,state):
    budget=scope.memory_budget(role)
    if state.get('memory_budget')!=budget:raise ValueError('V66 resolved/live memory profile')
    journal=Journal(folder,window_scope=scope.window,planning_limit_bytes=budget['planning_gib']*2**30);journal.source_state=state
    if role=='PREFLIGHT':return preflight(folder,journal)
    if role=='PREPARE':return prepare_body(folder,journal,scope_module=scope,boundary_provider=fresh_boundaries,identity_key='body_identity')
    if role in scope.SOLVES:
        from .independent_tetra_study import solve
        return solve(role,folder,journal,state,scope_module=scope,prepared_provider=prepared_provider,
            action_factory=lambda s,b:CoefficientFullAction(s,b,13))
    if role in ('COMPARE_GATE','VERIFY_COST'):
        from benchmarks.collect_frozen_local_h import verify
        return verify(role,folder,journal)
    raise ValueError('V66 explicit one-run inventory')
