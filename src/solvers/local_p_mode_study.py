"""Thin parameterization of the existing full tetra preparation/solve chain."""
import gc
import hashlib
import json
import subprocess
import numpy as np
from src.runners.task042_shared import write_json
from . import local_p_mode_scope as scope
from . import independent_tetra_reference as core
from .p6_completion_study import setup_identity,prepare as prepare_body
from .frozen_local_h_study import fresh_boundaries
from .scattering_anchor import Journal,save_arrays
from .tetra_body_checkpoint import load_checkpoint,body_fingerprint
from .tetra_coefficient_action import CoefficientFullAction


def body_quadrature(spec):return 2*spec['degree']+5


def entity_inventory(s):
    """Count actual independent moments on unique entities, not a p4 ratio."""
    b=s['V'].element.basix_element;degree=s['spec']['degree'];masters=s['masters']
    cells=np.asarray([s['V'].dofmap.cell_dofs(c) for c in range(s['spec']['cells'])])
    counts={}
    for dim in (1,2,3):
        local=[i for entity in b.entity_dofs[dim] for i in entity]
        ids=np.unique(cells[:,local]);counts[dim]=len(np.intersect1d(ids,masters,assume_unique=True))
    mult={1:degree,2:degree*(degree-1),3:degree*(degree-1)*(degree-2)//2}
    if any(counts[d]%mult[d] for d in counts):raise ValueError('independent complete entity moments')
    if sum(counts.values())!=s['P'].shape[1]:raise ValueError('entity/MPC dimension identity')
    return dict(independent_edges=counts[1]//mult[1],independent_faces=counts[2]//mult[2],cells=counts[3]//mult[3],
        independent_moments={str(d):n for d,n in counts.items()},formula_dimension=sum(counts.values()))


def preflight(folder,journal):
    # Reuse the qualified p5 kernel by exact source bytes, not an old PDE replay.
    old_path=scope.ROOT/'docs/task042_neural_coarse_inverse/outcomes/records/kernel_qualification_v65.json'
    old=json.loads(old_path.read_text());kernel='src/solvers/tetra_coefficient_action.py'
    qualified=subprocess.check_output(['git','show',old['source']+':'+kernel],cwd=scope.ROOT)
    if qualified!=(scope.ROOT/kernel).read_bytes() or not old['pass_gate'] or old['saved_p5']['relative']>1e-10:raise ValueError('same-blob p5 original-action qualification')
    s=core.make_setup(scope.case_spec('PREFLIGHT'),scope.physical_for('PREFLIGHT'),journal)
    b=s['V'].element.basix_element
    if (b.dim,b.embedded_superdegree)!=(140,5):raise ValueError('actual p5 basis/superdegree')
    entities=entity_inventory(s);actual=s['P'].shape[1]
    if entities['cells']!=25576:raise ValueError('fixed mesh cell identity')
    s['spec'].update(independent=actual,rows=actual+828)
    s['physical']['discretization'].update(FE=actual,rows=actual+828)
    identity,arrays=setup_identity(s);cap=core.assembly_capacity(s,journal)
    rng=np.random.default_rng(6701);P=s['P'];x=rng.normal(size=P.shape[1])+1j*rng.normal(size=P.shape[1]);y=rng.normal(size=P.shape[0])+1j*rng.normal(size=P.shape[0]);px=P@x
    dual=abs(np.vdot(px,y)-np.vdot(x,P.conj().T@y))/max(np.linalg.norm(px)*np.linalg.norm(y),1e-300)
    stored=save_arrays(folder/'actual_frozen_p5_identity.npz',**arrays)
    result=dict(status='COMPLETED',pass_gate=dual<=1e-12,assembly_admitted=cap['admitted'],body_identity=identity,
        actual_L5_spec=s['spec'],entity_inventory=entities,capacity=cap,complex_dual=dual,frozen_mesh_arrays=stored,
        actual=dict(cells=25576,native=P.shape[0],independent=actual,rows=actual+828,degree=5,local_dim=140,superdegree=5,
            notch_tetrahedra=int(np.count_nonzero((s['geometry']['regular_tags']==s['cfg'].tags.grating)&(s['geometry']['cell_tags']==s['cfg'].tags.air)))),
        kernel_qualification=dict(path=str(old_path),sha256=hashlib.sha256(old_path.read_bytes()).hexdigest(),kernel_sha256=hashlib.sha256(qualified).hexdigest(),
            original_source=old['source'],p5_relative=old['saved_p5']['relative'],replayed=False),
        new_body_builds=0,new_numeric_factors=0,new_complete_solves=0,new_full_body_actions=0,source=journal.source_state,timings=journal.timings)
    write_json(folder/'preflight_qualification.json',result);del s;gc.collect();return result


def prepared_provider(s,folder,journal):
    from .independent_tetra_study import load_boundary
    role=journal.source_state['stage'].split('-',1)[1];p=scope.prepared_parent(role);identity,_=setup_identity(s)
    changed=role=='M4'
    with journal.measured('readonly_explicit_parent_body_K_identity_and_reopen'):
        K,m,arrays=load_checkpoint(p['checkpoint'],identity,allow_mode_change=changed)
    if changed:
        b,o=fresh_boundaries(s,folder,journal)
        journal.event('same_body_new_complete_modes',producer_namespace='v66',producer_role='PREPARE',
            producer_body_fingerprint=body_fingerprint(m['identity']),consumer_body_fingerprint=body_fingerprint(identity),
            new_boundary_modes=1188,old_boundary_not_used=True)
    else:
        with journal.measured('checked_readonly_this_case_q47_q63'):
            b=load_boundary(s,p['boundary_arrays'],p['mode_sha256'],'q47');o=load_boundary(s,p['boundary_arrays'],p['mode_sha256'],'q63')
    return dict(K=K,form=m['form'],boundary=b,oracle=o,owners=arrays,checkpoint=p['checkpoint'])


def execute(role,folder,state):
    budget=scope.memory_budget(role)
    if state.get('memory_budget')!=budget:raise ValueError('V67 resolved/live profile')
    journal=Journal(folder,window_scope=scope.window,planning_limit_bytes=budget['planning_gib']*2**30);journal.source_state=state
    if role=='PREFLIGHT':return preflight(folder,journal)
    if role=='PREPARE':return prepare_body(folder,journal,scope_module=scope,boundary_provider=fresh_boundaries,identity_key='body_identity')
    if role in scope.SOLVES:
        from .independent_tetra_study import solve
        return solve(role,folder,journal,state,scope_module=scope,prepared_provider=prepared_provider,
            action_factory=lambda s,b:CoefficientFullAction(s,b,body_quadrature(s['spec'])))
    if role=='VERIFY_COST':
        from benchmarks.collect_local_p_modes import verify
        return verify(folder,journal)
    raise ValueError('V67 explicit one-run inventory')
