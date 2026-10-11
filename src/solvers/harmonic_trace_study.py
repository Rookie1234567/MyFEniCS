"""Thin harmonic preparation adapter; iteration and field tail stay shared."""
import copy
import gc
import json
import time

import numpy as np

from src.runners.task042_shared import write_json
from . import harmonic_trace_scope as scope
from . import bounded_trace_study as common
from .scattering_anchor import Journal,relative,save_arrays
from .scattering_anchor_checks import checked_arrays
from .bounded_trace_pc import csr_load,csr_save
from .harmonic_trace_coarse import macro_partition,build_harmonic,HarmonicTransfer


def preflight(folder,journal,state):
    old=scope.checked_json(scope.plan_record()['reuse_qualification'])
    if not old['mathematics_pass']:raise ValueError('immutable parent mathematics')
    p=scope.parent_preparation()
    if len(p['matrices'])!=38 or p['coarse_inventory']['independent_FE']!=6240:raise ValueError('fixed parent patch/coarse')
    # Macro geometry is the actual original960tet, without forms or PDE.
    s=common.core.make_setup(scope.case_spec('PREFLIGHT'),scope.physical_for('PREFLIGHT'),journal)
    ph=copy.deepcopy(scope.plan_record()['physical_descriptor']);z=ph['geometry']['axes_nm']['z']
    ph['geometry']['axes_nm']['z']=[l+(r-l)*j/2 for l,r in zip(z[:-1],z[1:]) for j in range(2)]+[z[-1]]
    spec=dict(case='NOTCH',degree=2,h_ratio=1,cells=960,independent=6240,complete_modes=828,notch_tetrahedra=24)
    parent=common.core.make_setup(spec,ph,journal)
    xyz=parent['mesh'].geometry.x[parent['mesh'].geometry.dofmap].copy()
    Zarr=checked_arrays(p['Z']);Z=csr_load(p['Z']);a=common.service(journal,scope=scope)
    with journal.measured('real_parent_face_closure_and_periodic_master_partition'):
        owner,inventory=macro_partition(s,a,Zarr['parent_cells'],xyz)
    arrays=save_arrays(folder/'macro_partition.npz',owner=owner,parent_cells=Zarr['parent_cells'],parent_geometry=xyz)
    supported=np.unique(Z[owner<0].indices)
    if len(supported)!=6240:raise ValueError('p2 skeleton entity column coverage')
    inventory.update(p2_entity_columns=len(supported),skeleton_old_Z0= p['Z'],no_new_Z0_or_partition=True)
    result=dict(status='COMPLETED',pass_gate=True,partition=arrays,inventory=inventory,
        immutable_mathematics=scope.plan_record()['reuse_qualification'],source=state,
        local_numeric_count=0,new_complete_solves=0,global_fine_matrix_reads=0,timings=journal.timings)
    write_json(folder/'macro_partition_qualification.json',result);return result


def prepare(folder,journal,state):
    scope.require_stage('HARMONIC_PREPARE');p=scope.parent_preparation();pref=scope.stage('PREFLIGHT')
    part=checked_arrays(pref['partition']);Z0=csr_load(p['Z'])
    # Use the original coordinate scaling, not a new physical normalization.
    s,b,oracle,a,rhs,left,right=common.setup_service('HARMONIC_PREPARE',journal,scope=scope)
    checkpoint=scope.ARTIFACT/'harmonic_lifts';checkpoint.mkdir(exist_ok=True)
    identity=dict(partition_sha256=pref['partition']['sha256'],Z0_sha256=p['Z']['sha256'],packet_sha256=a.receipt['sha256'],
        left_sha256=__import__('hashlib').sha256(left.tobytes()).hexdigest(),right_sha256=__import__('hashlib').sha256(right.tobytes()).hexdigest(),
        mathematical_source_sha256=__import__('hashlib').sha256((scope.ROOT/'src/solvers/harmonic_trace_coarse.py').read_bytes()).hexdigest())
    ip=checkpoint/'identity.json'
    if ip.exists() and json.loads(ip.read_text())!=identity:raise ValueError('healthy macro reuse exact mathematical identity')
    write_json(ip,identity)
    def live():
        scope.window.require_live()
        if scope.window.case_remaining(active=True)<=0:raise RuntimeError('V74 cumulative H preparation cap')
    with journal.measured('all_macro_harmonic_preparation'):
        transfer,EH=build_harmonic(a,Z0,part['owner'],left,right,checkpoint,journal,require_live=live)
    transfer['identity']=identity;ZH=HarmonicTransfer.load(transfer)
    coarse=csr_save(folder/'coarse_EH.npz',EH);analysis=common.symbolic(EH,journal,'harmonic_coarse')
    total=sum(row['double_bytes'] for row in p['analysis'])+analysis['double_bytes']
    qualification=[];rng=np.random.default_rng(7403)
    for j in range(2):
        w=rng.normal(size=7068)+1j*rng.normal(size=7068);v=ZH.prolong(w)
        orig=common.action_charge('Q_H_Galerkin',lambda:left*a.apply_trace(right*v),scope=scope)
        pulled=ZH.restrict(orig);target=EH@w
        dual=abs(np.vdot(v,orig)-np.vdot(w,pulled))/max(np.linalg.norm(v)*np.linalg.norm(orig),1e-300)
        homogeneous=relative(orig[:a.nt][part['owner']>=0],orig)
        bound=np.zeros_like(v.real);bound[:a.nt]=abs(a.Ctilde)@abs(right[a.nt:]*w[6240:])
        for _,_,ids,E,key in a.cell_records:np.add.at(bound,ids,abs(E).T@(abs(a.cache[key]['schur'])@(abs(E)@abs(v[ids]))))
        operation= float(np.linalg.norm(orig[:a.nt][part['owner']>=0])/max(np.linalg.norm(bound),1e-300))
        row=dict(Galerkin_relative=relative(pulled-target,target),dual_operation_scaled=float(dual),
            homogeneous_relative=homogeneous,homogeneous_operation_scaled=operation,
            homogeneous_absolute=float(np.linalg.norm(orig[:a.nt][part['owner']>=0])),
            arrays=save_arrays(folder/f'harmonic_witness{j}.npz',w=w,prolonged=v,original=orig,pulled=pulled,coarse_action=target))
        qualification.append(row)
    passed=all(max(r[k] for k in ('Galerkin_relative','dual_operation_scaled','homogeneous_relative','homogeneous_operation_scaled'))<=1e-10 for r in qualification)
    result=dict(status='COMPLETED' if passed and total<=80*2**30 else 'MATH_GATE_FAILED' if not passed else 'CAPACITY_BLOCKED',
        pass_gate=passed and total<=80*2**30,transfer=transfer,coarse_matrix=coarse,coarse_symbolic=analysis,
        double_symbolic_sum_bytes=total,double_symbolic_sum_limit_bytes=80*2**30,qualification=qualification,
        partition=pref,global_fine_K_or_S_reads=0,global_fine_K_or_S_formations=0,
        local_macro_numeric=transfer['macro_numeric_count'],new_complete_solves=0,source=state,timings=journal.timings)
    write_json(folder/'harmonic_preparation.json',result);a.release_hot();return result


def execute(role,folder,state):
    budget=scope.memory_budget(role)
    if state.get('memory_budget')!=budget:raise ValueError('V74 resolved/live memory contract')
    journal=Journal(folder,window_scope=scope.window,planning_limit_bytes=budget['planning_gib']*2**30);journal.source_state=state
    if role=='PREFLIGHT':return preflight(folder,journal,state)
    if role=='HARMONIC_PREPARE':return prepare(folder,journal,state)
    if role=='HARMONIC':
        if state.get('postprocessing_resume'):return common.consume_interrupted_retained(role,folder,journal,state,scope=scope)
        return common.iterate(folder,journal,state,scope=scope,role=role)
    if role=='VERIFY_COST':
        from benchmarks.collect_harmonic_trace import verify
        return verify(folder,journal)
    raise ValueError('V74 explicit one-run role')
