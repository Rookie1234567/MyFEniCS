"""V15 independent frozen-number/hash checker; never solves or trains."""
import math
from pathlib import Path
import numpy as np
from src.io.actual_loss_block_descent_check import verified_field_gate
from src.solvers.neural_fe_action_packet import array_hash,file_hash


def finite(v):return isinstance(v,(int,float)) and math.isfinite(v)
def head_numeric(row,columns):
    return (row.get('rank_A')==columns and all(finite(row.get(k)) and row[k]<=limit
        for k,limit in [('actual_vs_thin_fixed_rhs',1e-8),('stationarity_UHr_fixed_rhs',1e-8),('Hhat_solve_operation_relative',1e-12)]))
def manufactured(row,columns):
    return (head_numeric(row['numeric'],columns) and row['numeric']['schur_relative']<=1e-8
        and row['known_z_relative']<=1e-6 and row['homogeneous_recovery_operation_relative']<=1e-10
        and row.get('full_manufactured_RHS_from_original_action') and not row.get('reference_used')
        and not row.get('physical_b_overwritten'))
def frozen_state(record,columns=None):
    path=Path(record['path'])
    if file_hash(path)!=record['sha256']:return False
    with np.load(path,allow_pickle=False) as data:
        if data['trace'].shape!=(18144,) or data['port'].shape!=(40,) or data['z'].shape!=(18184,):return False
        if columns is not None and data['c'].shape!=(columns,):return False
        if not np.array_equal(data['z'],np.r_[data['trace'],data['port']]):return False
        for key in data.files:
            if key+'_sha256' in record and array_hash(data[key])!=record[key+'_sha256']:return False
        return all(np.isfinite(data[k]).all() for k in data.files)
def check_v15(setup,solves,verify):
    from src.solvers.local_trace_head import LIMITS
    problems=[];qualification={};states={};recomputed={}
    packet=setup['operator_packet']
    if file_hash(packet['path'])!=packet['sha256']:problems.append('physical_action_hash')
    with np.load(packet['path'],allow_pickle=False) as data:bnorm=float(np.linalg.norm(data['b']))
    common=setup['capacity']['common_rank_by_patch'];ranks=setup['capacity']['original_rank_by_family']
    capacity=(len(common)==8 and common==[min(a,b,195) for a,b in zip(ranks['POLY'],ranks['NN'],strict=True)]
        and sum(common)==setup['capacity']['actual_columns'] and all(0<x<=195 for x in common))
    if not capacity:problems.append('paired_capacity')
    record=setup['entity_map']
    if file_hash(record['path'])!=record['sha256']:problems.append('entity_map_hash')
    with np.load(record['path'],allow_pickle=False) as data:
        if not np.array_equal(data['row'],np.arange(18144)) or np.bincount(data['patch_id'],minlength=8).tolist()!=setup['entity_checks']['patch_rows']:
            problems.append('canonical_entity_cover')
        for d,e in set(zip(data['entity_dim'],data['entity_id'])):
            mask=(data['entity_dim']==d)&(data['entity_id']==e)
            if len(np.unique(data['patch_id'][mask]))!=1:problems.append('entity_split')
    mapping_ok=all(row['interpolation_relative']<=1e-10 and row['MPC_expansion_relative']<=1e-10 and row['slave_zero_before']==0 for row in setup['interpolation_checks'])
    block_ok=all(max(row['forward_relative'],row['adjoint_operation_relative'],row['orthogonality'])<=1e-10 for row in setup['decoder_checks'].values())
    if (mapping_ok and block_ok)!=setup['local_setup_qualified']:problems.append('setup_saved_status')
    for name,row in solves.items():
        if row.get('reference_arrays_read'):problems.append(name+'.reference_feedback')
        if 'physical' not in row:continue
        columns=row['basis']['actual_columns'];p=row['physical']
        qualified=head_numeric(p['numeric'],columns)
        qualified &= row['basis']['Q_orthogonality']<=1e-10 and row['basis']['Hhat_condition']<=1e10
        qualified &= max(row['basis']['original_action_pairing'])<=1e-10
        if name.startswith('LOCAL_'):qualified &= manufactured(row['witness'],columns)
        else:qualified &= row['checks']['G0_reconstruction']<=1e-10 and p['numeric']['Phi']<=row['checks']['origin_Phi']+row['checks']['margin']
        if qualified!=row['decoder_qualified']:problems.append(name+'.decoder_status')
        qualification[name]=bool(qualified);states[name]=frozen_state(p['state'],columns)
        with np.load(p['state']['path'],allow_pickle=False) as data:
            residual=np.array(data['residual']);schur=float(np.linalg.norm(residual)/bnorm)
            Phi=float(np.vdot(residual,residual).real/(2*bnorm**2))
            from src.solvers.local_trace_study import decoder_from
            if name.startswith('LOCAL_'):
                decoder=decoder_from(p['decoder_identity'])
            else:
                from src.solvers.local_trace_decoder import UnionTraceDecoder
                identity=p['decoder_identity'];g=identity['G0'];u=identity['complement']
                if file_hash(g['path'])!=g['sha256'] or file_hash(u['path'])!=u['sha256']:problems.append(name+'.union_hash')
                decoder=UnionTraceDecoder(np.load(g['path'],mmap_mode='r'),np.load(u['path'],mmap_mode='r')[:,:identity['matched_q']])
            decoded=decoder@data['c']
            trace_difference=float(np.linalg.norm(decoded-data['trace'])/max(np.linalg.norm(data['trace']),1e-300))
            recomputed[name]=dict(Phi=Phi,Schur=schur,decoder_trace_relative=trace_difference)
            if abs(Phi-p['numeric']['Phi'])>1e-12 or abs(schur-p['numeric']['schur_relative'])>1e-12 or trace_difference>1e-10:problems.append(name+'.raw_vector_norm_or_decoder')
            del decoder,decoded
    if not all(states.values()):problems.append('frozen_state_identity')
    if not verify.get('reference_only_after_solver_frozen') or verify.get('reference_feedback_to_solver'):problems.append('reference_barrier')
    reference_ok=finite(verify['reference_audit']['audit'].get('independent_DOLFINx_total_native_relative')) and verify['reference_audit']['audit']['independent_DOLFINx_total_native_relative']<=1e-10
    independent={name:reference_ok and verified_field_gate(row) and row['audit']['schur_original_identity_operation_relative']<=1e-10 and all(row['fields'][k]<=1e-4 for k in ('scattered_FE_L2_relative','scattered_scaled_curl_relative'))
                 for name,row in verify.get('rows',{}).items()}
    for name,passed in independent.items():
        if passed!=(verify['rows'][name]['status']=='SAME_DISCRETE_QUALIFIED'):problems.append(name+'.field_status')
    if any(verify['budget_counts'].get(k,math.inf)>v for k,v in LIMITS.items()) or verify['all_batch_equivalent_actions']>12000:problems.append('batch_caps')
    return dict(status='EVIDENCE_CONSISTENT' if not problems else 'RAW_MISMATCH',mismatches=problems,
        raw_residual_and_decoder_recomputed=recomputed,paired_capacity=capacity,matched_rank_by_patch=common,matched_columns=sum(common),
        independent_mapping_qualified=mapping_ok,block_decoder_qualified=block_ok,
        numerical_qualification=qualification,frozen_state_identity=states,strict_same_discrete=independent,
        strict_qualified_states=sum(independent.values()),saved_statuses_not_trusted=True,
        solver_or_hidden_training_qualification_claimed=False)
