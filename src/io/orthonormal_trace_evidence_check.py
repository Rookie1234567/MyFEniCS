"""Raw-field V14 evidence checker; never executes a numerical solver."""
import math
from pathlib import Path
import numpy as np
from src.io.actual_loss_block_descent_check import verified_field_gate
from src.solvers.neural_fe_action_packet import array_hash,file_hash

def finite(v):return isinstance(v,(int,float)) and math.isfinite(v)
def decoder_numeric(row):
    endpoints=row.get('A_singular_range',[0,0])
    return (row.get('rank_A')==1560 and len(endpoints)==2
        and 0<endpoints[0]<=endpoints[1] and endpoints[0]>1e-12*endpoints[1]
        and row.get('driver')=='gelsd' and row.get('cond')==1e-12
        and row.get('correction_count',2)<=1 and not row.get('exact_optimum_claimed')
        and all(finite(row.get(k)) and row[k]<=limit
        for k,limit in [('actual_vs_thin_fixed_rhs',1e-8),('stationarity_UHr_fixed_rhs',1e-8),('Hhat_solve_operation_relative',1e-12)]))
def basis_numeric(row):
    endpoints=row.get('P_singular_range',[0,0])
    return (row.get('rank_P')==1560 and len(endpoints)==2
        and 0<endpoints[0]<=endpoints[1] and endpoints[0]>1e-12*endpoints[1]
        and row.get('Hhat_condition',math.inf)<=1e10
        and all(finite(row.get(k)) and row[k]<=1e-10 for k in ('P_reconstruction','Q_orthogonality'))
        and not row.get('raw_gamma_writeback') and row.get('main_forward')=='trace_EQUALS_Q_times_c')
def manufactured(row):
    return (decoder_numeric(row['numeric']) and row['numeric']['schur_relative']<=1e-8
        and row['known_z_relative']<=1e-6 and row['homogeneous_recovery_operation_relative']<=1e-10
        and row.get('full_manufactured_RHS_from_original_action')
        and not row.get('reference_used') and not row.get('physical_b_overwritten'))
def frozen_state(record):
    path=Path(record['path'])
    if file_hash(path)!=record['sha256']:return False
    with np.load(path,allow_pickle=False) as data:
        sizes=dict(hidden=(8576,),c=(1560,),trace=(18144,),port=(40,),z=(18184,))
        if any(data[k].shape!=size for k,size in sizes.items()):return False
        if data['hidden'].dtype!=np.float64 or any(data[k].dtype!=np.complex128 for k in ('c','trace','port','z')):return False
        if np.iscomplexobj(data['hidden']) or not np.array_equal(data['z'],np.r_[data['trace'],data['port']]):return False
        for key in data.files:
            if key+'_sha256' not in record or array_hash(data[key])!=record[key+'_sha256']:return False
        return all(np.isfinite(data[k]).all() for k in data.files)
def retained_Q_pair(point,path):
    if file_hash(Path(path))!=point['decoder_identity']['sha256']:
        return dict(qualified=False,reason='Q_file_hash')
    Q=np.load(path,mmap_mode='r',allow_pickle=False)
    with np.load(point['state']['path'],allow_pickle=False) as data:
        difference=np.linalg.norm(Q@data['c']-data['trace'])/max(np.linalg.norm(data['trace']),1e-300)
    return dict(qualified=bool(difference<=1e-10),actual_Qc_relative=float(difference),
        original_action_calls=0,Q_sha256=point['decoder_identity']['sha256'])
def check_v14(decoder,profile,verify):
    problems=[]
    origins=decoder.get('origin')
    qualified=(bool(origins) and basis_numeric(decoder['basis']) and decoder_numeric(origins['numeric'])
        and len(decoder['witnesses'])==2 and all(manufactured(r) for r in decoder['witnesses']))
    if qualified!=decoder['decoder_qualified']:problems.append('decoder_saved_status')
    if any(row.get('reference_arrays_read') for row in (decoder,profile)):problems.append('solver_reference_feedback')
    if not profile.get('queue_frozen') or not verify.get('reference_only_after_solver_frozen') or verify.get('reference_feedback_to_solver'):
        problems.append('freeze_reference_barrier')
    identity={p['name']:frozen_state(p['state']) for p in profile.get('points',[])}
    if not all(identity.values()):problems.append('state_hash_shape')
    pairs={}
    if profile.get('selected'):
        for name,path in [('ORIGIN',profile['origin_Q_path']),(profile['selected'],profile['selected_Q_path'])]:
            point=next(p for p in profile['points'] if p['name']==name)
            pairs[name]=retained_Q_pair(point,path)
        if not all(row['qualified'] for row in pairs.values()):problems.append('retained_Qc_identity')
    for p in profile.get('points',[]):
        if decoder_numeric(p['numeric'])!=p['numeric']['decoder_gate']:problems.append(p['name']+'.decoder_status')
    independent={name:(verified_field_gate(row) and finite(row['audit'].get('schur_original_identity_operation_relative'))
        and row['audit']['schur_original_identity_operation_relative']<=1e-10)
        for name,row in verify.get('rows',{}).items()}
    for name,passed in independent.items():
        if passed!=(verify['rows'][name]['status']=='SAME_DISCRETE_QUALIFIED'):problems.append(name+'.field_status')
    limits=dict(basis_evaluations=10,thin_LS_calls=24,thin_RHS=28,original_audits=80,new_profiles=2,field_states=10)
    if any(verify['budget_counts'].get(k,math.inf)>v for k,v in limits.items()) or verify['all_batch_equivalent_actions']>18000:
        problems.append('budget')
    comparison_margin=max(1e-10,100*decoder['sensitivity']['delta_basis'])
    if profile['O3'].get('evaluated_s') and not profile['O3']['progress']['O3_admitted']:
        problems.append('O3_without_pre_registered_progress')
    if profile.get('selected'):
        eligible=[p for p in profile['points'] if p.get('progress_vs_origin',{}).get('qualified_for_selection',p['name']=='ORIGIN')]
        if profile['selected']!=min(eligible,key=lambda p:p['numeric']['Phi'])['name']:
            problems.append('selection_not_original_Phi')
    return dict(status='EVIDENCE_CONSISTENT' if not problems else 'RAW_MISMATCH',mismatches=problems,
        decoder_qualified=qualified,state_identity=identity,retained_Qc_identity=pairs,strict_same_discrete=independent,
        physical_qualified_candidates=sum(independent.values()),saved_statuses_not_trusted=True,
        micro_qualified=any(independent.values()),global_p4_factor_allowed=False,
        comparison_margin_observed_basis=comparison_margin,
        new_reference_native_scalar='not persisted by reused verifier; no candidate qualified; old REF7 qualification remains bound')
