"""Thin V75 adapter: old healthy lifts, durable base, shared iterative tail."""
import ast
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np

from src.runners.task042_shared import write_json
from . import durable_harmonic_scope as scope
from . import bounded_trace_study as common
from .scattering_anchor import Journal,relative,save_arrays
from .scattering_anchor_checks import checked_arrays
from .bounded_trace_pc import csr_load,csr_save
from .harmonic_trace_coarse import macro_blocks,build_harmonic,HarmonicTransfer
from .durable_galerkin import durable_base,paired_products


def formula_fingerprints(text):
    nodes=ast.parse(text).body
    names=('macro_blocks','local_extension','HarmonicTransfer')
    return {n.name:hashlib.sha256(ast.dump(n,include_attributes=False).encode()).hexdigest()
        for n in nodes if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names}


def preflight(folder,journal,state):
    plan=scope.plan_record();p=scope.parent_preparation();assets=plan['harmonic_parent']
    pref=scope.checked_json(assets['partition_producer']);part=checked_arrays(pref['partition'])
    parent=Path(assets['lift_folder']);identity=scope.checked_json(assets['identity'])
    s,b,oracle,a,rhs,left,right=common.setup_service('PREFLIGHT',journal,scope=scope)
    Z0=csr_load(p['Z']);ZB=Z0.multiply((part['owner']<0)[:,None]).tocsr();ZB.eliminate_zeros()
    expected=dict(partition_sha256=pref['partition']['sha256'],Z0_sha256=p['Z']['sha256'],packet_sha256=a.receipt['sha256'],
        left_sha256=hashlib.sha256(left.tobytes()).hexdigest(),right_sha256=hashlib.sha256(right.tobytes()).hexdigest())
    if any(identity[k]!=v for k,v in expected.items()):raise ValueError('old harmonic mathematical inputs changed')
    old_text=subprocess.check_output(['git','show','11b3011f97587877adf58814e36b83d0e099c6e9:src/solvers/harmonic_trace_coarse.py'],cwd=scope.ROOT,text=True)
    if hashlib.sha256(old_text.encode()).hexdigest()!=identity['mathematical_source_sha256']:raise ValueError('old macro source blob identity')
    current=(scope.ROOT/'src/solvers/harmonic_trace_coarse.py').read_text()
    if formula_fingerprints(old_text)!=formula_fingerprints(current):raise ValueError('harmonic block or full dual mathematics changed')
    rows=[];seen=set()
    for rp in sorted(parent.glob('macro[0-9][0-9][0-9][0-9].json')):
        old=json.loads(rp.read_text());lift=checked_arrays(old['lift']);cor=checked_arrays(old['correction']);j=old['macro']
        if j in seen or not np.array_equal(lift['rows'],np.flatnonzero(part['owner']==j)):raise ValueError('old lift unique owner')
        if len(np.unique(lift['columns']))!=len(lift['columns']) or np.any(lift['columns']>=7068):raise ValueError('old lift column map')
        if lift['values'].shape!=(len(lift['rows']),len(lift['columns'])) or cor['values'].shape!=(len(lift['columns']),)*2:raise ValueError('lift/correction pairing')
        if not np.isfinite(lift['values']).all() or not np.isfinite(cor['values']).all():raise ValueError('old lift nonfinite')
        seen.add(j);rows.append(dict(macro=j,path=str(rp),sha256=hashlib.sha256(rp.read_bytes()).hexdigest(),rows=len(lift['rows'])))
    if sorted(seen)!=list(range(881)):raise ValueError('expected healthy881, missing79 inventory')
    ids=sorted(set((0,880,max(rows,key=lambda r:(r['rows'],-r['macro']))['macro'])))
    witnesses=[]
    for j in ids:
        old=json.loads((parent/f'macro{j:04d}.json').read_text());v=checked_arrays(old['lift']);c=checked_arrays(old['correction'])
        cells=[r[0] for r in a.cell_records if np.any(part['owner'][r[2]]==j)]
        A,AJQ,AQJ,cols=macro_blocks(a,cells,v['rows'],ZB,left,right)
        if not np.array_equal(cols,v['columns']):raise ValueError('macro compatibility column map')
        residual=A@v['values']+AJQ;correction=AQJ@v['values']
        row=dict(macro=j,local_relative=relative(residual,AJQ),local_operation_scaled=relative(residual,abs(A)@abs(v['values'])+abs(AJQ)),
            correction_relative=relative(correction-c['values'],c['values']),
            arrays=save_arrays(folder/f'compatibility_macro{j:04d}.npz',residual=residual,AJQ=AJQ,correction=correction,saved_correction=c['values']),
            new_numeric_count=0)
        witnesses.append(row)
    if any(max(r[k] for k in ('local_relative','local_operation_scaled','correction_relative'))>1e-10 for r in witnesses):raise ValueError('actual macro mathematical compatibility failed')
    # One fixed bounded pairing. Cell maps and Schur values are never merged.
    representatives={}
    for r in a.cell_records:
        z=ZB[r[2]];signature=(len(np.unique(z.indices)),r[3].shape,r[3].nnz)
        representatives.setdefault(signature,r)
    records=sorted(list(representatives.values())[:64],key=lambda r:r[0])
    pair=paired_products(a,ZB,records,folder,journal)
    result=dict(status='COMPLETED',pass_gate=True,partition=pref,compatibility=dict(pass_gate=True,
        old_identity=identity,mathematical_inputs=expected,parent_producer_source=assets['producer_source'],current_consumer_source=state['source_sha'],
        parent_folder=str(parent),healthy_macro_ids=sorted(seen),healthy_records=rows,witnesses=witnesses,
        unchanged_formula_fingerprints=formula_fingerprints(current),source_change_reason='durable base/cache/accounting only; exact macro blocks, local equations and complete dual unchanged',
        new_numeric_count=0,not_a_reaudit_of_all_local_residuals=True),batch_pair=pair,
        source=state,new_global_actions=0,new_numeric_count=0,new_KSP_solves=0,timings=journal.timings)
    write_json(folder/'reuse_compatibility.json',result);a.release_hot();return result


def prepare(folder,journal,state):
    scope.require_stage('HARMONIC_PREPARE');p=scope.parent_preparation();pref=scope.stage('PREFLIGHT')
    original=pref['partition'];part=checked_arrays(original['partition']);Z0=csr_load(p['Z'])
    s,b,oracle,a,rhs,left,right=common.setup_service('HARMONIC_PREPARE',journal,scope=scope)
    checkpoint=scope.ARTIFACT/'harmonic_lifts';checkpoint.mkdir(exist_ok=True)
    compatibility=pref['compatibility'];identity=compatibility['mathematical_inputs']
    ip=checkpoint/'identity.json'
    if ip.exists() and json.loads(ip.read_text())!=identity:raise ValueError('V75 partial macro checkpoint inputs changed')
    if not ip.exists():write_json(ip,identity)
    def live():scope.window.require_live()
    def base_provider(service,ZB,l,r):
        A,manifest=durable_base(service,ZB,l,r,scope.ARTIFACT/'base_blocks',journal,
            identity=identity,require_live=live,batched=pref['batch_pair']['selected']=='batch')
        write_json(folder/'base_checkpoint_manifest.json',manifest);return A
    transfer,EH=build_harmonic(a,Z0,part['owner'],left,right,checkpoint,journal,require_live=live,
        base_provider=base_provider,parent_folder=compatibility['parent_folder'],reuse_compatibility=compatibility,future_reserve_bytes=12*2**30)
    transfer['identity']=identity;ZH=HarmonicTransfer.load(transfer)
    coarse=csr_save(folder/'coarse_EH.npz',EH);analysis=common.symbolic(EH,journal,'harmonic_coarse')
    total=sum(r['double_bytes'] for r in p['analysis'])+analysis['double_bytes']
    qualification=[];rng=np.random.default_rng(7403)
    for j in range(2):
        w=rng.normal(size=7068)+1j*rng.normal(size=7068);v=ZH.prolong(w)
        orig=common.action_charge('Q_H_Galerkin',lambda:left*a.apply_trace(right*v),scope=scope)
        pulled=ZH.restrict(orig);target=EH@w
        row=dict(Galerkin_relative=relative(pulled-target,target),
            dual_operation_scaled=float(abs(np.vdot(v,orig)-np.vdot(w,pulled))/max(np.linalg.norm(v)*np.linalg.norm(orig),1e-300)),
            homogeneous_relative=relative(orig[:a.nt][part['owner']>=0],orig),
            homogeneous_absolute=float(np.linalg.norm(orig[:a.nt][part['owner']>=0])),
            arrays=save_arrays(folder/f'harmonic_witness{j}.npz',w=w,prolonged=v,original=orig,pulled=pulled,coarse_action=target))
        bound=np.zeros(len(v),float);bound[:a.nt]=abs(a.Ctilde)@abs(right[a.nt:]*w[6240:])
        for _,_,ids,E,key in a.cell_records:np.add.at(bound,ids,abs(E).T@(abs(a.cache[key]['schur'])@(abs(E)@abs(v[ids]))))
        row['homogeneous_operation_scaled']=float(row['homogeneous_absolute']/max(np.linalg.norm(bound),1e-300));qualification.append(row)
    rng=np.random.default_rng(7404);w=rng.normal(size=7068)+1j*rng.normal(size=7068)
    r=rng.normal(size=ZH.shape[0])+1j*rng.normal(size=ZH.shape[0]);v=ZH.prolong(w);dual=ZH.restrict(r)
    independent_dual=float(abs(np.vdot(v,r)-np.vdot(w,dual))/max(np.linalg.norm(v)*np.linalg.norm(r),1e-300))
    dual_receipt=save_arrays(folder/'independent_full_dual.npz',w=w,r=r,prolonged=v,pulled=dual)
    passed=independent_dual<=1e-10 and all(max(row[k] for k in ('Galerkin_relative','dual_operation_scaled','homogeneous_relative','homogeneous_operation_scaled'))<=1e-10 for row in qualification)
    result=dict(status='COMPLETED' if passed and total<=80*2**30 else 'MATH_GATE_FAILED' if not passed else 'CAPACITY_BLOCKED',pass_gate=passed and total<=80*2**30,
        transfer=transfer,coarse_matrix=coarse,coarse_symbolic=analysis,double_symbolic_sum_bytes=total,double_symbolic_sum_limit_bytes=80*2**30,
        qualification=qualification,independent_dual=dict(operation_scaled=independent_dual,arrays=dual_receipt),partition=original,
        reuse_compatibility=pref,source=state,new_complete_solves=0,global_fine_K_or_S_reads=0,global_fine_K_or_S_formations=0,timings=journal.timings)
    write_json(folder/'harmonic_preparation.json',result);a.release_hot();return result


def execute(role,folder,state):
    budget=scope.memory_budget(role)
    if state.get('memory_budget')!=budget:raise ValueError('V75 resolved/live budget')
    journal=Journal(folder,window_scope=scope.window,planning_limit_bytes=budget['planning_gib']*2**30);journal.source_state=state
    if role=='PREFLIGHT':return preflight(folder,journal,state)
    if role=='HARMONIC_PREPARE':return prepare(folder,journal,state)
    if role=='HARMONIC':
        if state.get('postprocessing_resume'):return common.consume_interrupted_retained(role,folder,journal,state,scope=scope)
        return common.iterate(folder,journal,state,scope=scope,role=role)
    if role=='VERIFY_COST':
        from benchmarks.collect_harmonic_trace import verify
        return verify(folder,journal,scope_module=scope)
    raise ValueError('V75 explicit one-run role')
