"""Thin, explicitly qualified parent binding for the existing tetra solver."""
import gc
import json
from pathlib import Path
from src.runners.task042_shared import write_json
from . import durable_l5_scope as scope
from . import independent_tetra_reference as core
from .p6_completion_study import setup_identity
from .scattering_anchor import Journal
from .tetra_body_checkpoint import load_checkpoint,file_digest
from .tetra_coefficient_action import CoefficientFullAction


def qualification():
    p=scope.plan_record()['original_qualification'];path=Path(p['path'])
    if file_digest(path)!=p['sha256']:raise ValueError('V68 original qualification hash')
    r=json.loads(path.read_text());parent=scope.prepared_parent('SOLVE_COMPLETE')
    if r['status']!='ORIGINAL_ACTION_VERIFIED' or r['checkpoint']!=parent['checkpoint'] or len(r['errors'])!=2 or max(r['errors'])>1e-10:
        raise ValueError('V68 original qualification and checkpoint binding')
    if r['source']['source_sha']!='53c01f124f090351747324b711599b2d8793e456':raise ValueError('original scientific producer')
    closure=scope.plan_record()['unchanged_numerical_closure']
    for name in closure:
        if file_digest(scope.ROOT/name)!=r['source']['implementation_hashes'][name]:raise ValueError('changed parent mathematical dependency: '+name)
    return r,p


def preflight(folder,journal):
    parent=scope.prepared_parent('SOLVE_COMPLETE');r,p=qualification()
    manifest=Path(parent['checkpoint']['path']);m=json.loads(manifest.read_text())
    if file_digest(manifest)!=parent['checkpoint']['sha256'] or (manifest.parent/'COMMIT').read_text().strip()!=parent['checkpoint']['sha256']:
        raise ValueError('V68 immutable COMMIT')
    s=core.make_setup(scope.case_spec('PREFLIGHT'),scope.physical_for('PREFLIGHT'),journal)
    identity,_=setup_identity(s)
    if identity!=m['identity'] or m['nnz']!=439529923 or m['bytes']!=8863726552:raise ValueError('V68 actual frozen L5 mathematical identity')
    if (s['V'].element.basix_element.dim,s['P'].shape)!=(140,(1979985,1943745)):raise ValueError('actual p5/MPC dimension')
    result=dict(status='COMPLETED',pass_gate=True,parent_namespace='v67',parent_role='PREPARE',
        parent_checkpoint=parent['checkpoint'],original_qualification=p,errors=r['errors'],
        actual_spec=s['spec'],body_identity=identity,source=journal.source_state,timings=journal.timings,
        new_body_builds=0,new_numeric_factors=0,new_complete_solves=0,new_full_body_actions=0,
        member_hash_validation='single sequential checked reopen in SOLVE_COMPLETE before numeric')
    write_json(folder/'resume_preflight.json',result);del s;gc.collect();return result


def prepared_provider(s,folder,journal):
    from .independent_tetra_study import load_boundary
    parent=scope.prepared_parent('SOLVE_COMPLETE');identity,_=setup_identity(s)
    with journal.measured('readonly_v67_p5_K_complete_member_hash_and_reopen'):
        K,m,arrays=load_checkpoint(parent['checkpoint'],identity)
    r,p=qualification()
    pairs=Path(scope.plan_record()['original_pairs']['path'])
    if file_digest(pairs)!=scope.plan_record()['original_pairs']['sha256']:raise ValueError('original pair receipt hash')
    old=json.loads(pairs.read_text())
    if old['errors']!=r['errors'] or old['arrays']!=r['arrays'] or old['form']!=m['form']:raise ValueError('original pair/form identity')
    if file_digest(Path(r['arrays']['path']))!=r['arrays']['sha256']:raise ValueError('original witness array bytes')
    with journal.measured('readonly_same_L5_q47_q63_checked_reopen'):
        b=load_boundary(s,parent['boundary_arrays'],parent['mode_sha256'],'q47')
        oracle=load_boundary(s,parent['boundary_arrays'],parent['mode_sha256'],'q63')
    journal.event('explicit_parent_reloaded',parent_namespace='v67',parent_role='PREPARE',
        checkpoint=parent['checkpoint'],qualification=p,no_body_build=True,no_factor_resume=True)
    return dict(K=K,form=m['form'],boundary=b,oracle=oracle,owners=arrays,checkpoint=parent['checkpoint'],
                qualification=p,reuse_original_pairs=old)


def execute(role,folder,state):
    budget=scope.memory_budget(role)
    if state.get('memory_budget')!=budget:raise ValueError('V68 resolved/live memory')
    journal=Journal(folder,window_scope=scope.window,planning_limit_bytes=budget['planning_gib']*2**30);journal.source_state=state
    if role=='PREFLIGHT':return preflight(folder,journal)
    if role=='SOLVE_COMPLETE':
        from .independent_tetra_study import solve
        return solve(role,folder,journal,state,scope_module=scope,prepared_provider=prepared_provider,
                     action_factory=lambda s,b:CoefficientFullAction(s,b,15))
    if role=='VERIFY_COST':
        from benchmarks.collect_durable_l5 import verify
        return verify(folder,journal)
    raise ValueError('V68 one-run stage inventory')
