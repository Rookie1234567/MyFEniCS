"""V13 independent raw-field checks; no PDE, fitting, or solver implementation."""

import math
from pathlib import Path

import numpy as np

from src.io.actual_loss_block_descent_check import verified_field_gate
from src.solvers.neural_fe_action_packet import array_hash, file_hash


def finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def vector_gate(record):
    rows=record.get('rows',[])
    for left,right in zip(rows,rows[1:]):
        if (all(finite(r.get('vector_relative')) and r['vector_relative']<=1e-5
                and r.get('parameter_and_trace_resolved') and r.get('tangent_norm',0)>0
                for r in (left,right)) and 0<right['h']<left['h']):
            return True
    return bool(record.get('extra') and vector_gate(record['extra']))


def dual_gate(checks):
    if set(checks)!={'421301','421302','actual_loss_barS_adjoint'}:
        return False
    for row in checks.values():
        if not all(finite(row.get(k)) for k in ('left','right','operation_scale')):
            return False
        if row['operation_scale']<=0 or abs(row['left']-row['right'])/row['operation_scale']>1e-9:
            return False
    return True


def tangent_gate(row):
    return (all(finite(row.get(k)) and row[k]<=1e-10 for k in
                ('value_rebuild_relative','port_tangent_identity','homogeneous_recovery_pair'))
            and row.get('port_tangent_norm',0)>0 and dual_gate(row['JVP_VJP'])
            and vector_gate(row['vector_FD']))


def joint_gate(row):
    return (all(finite(row.get(k)) and row[k]<=1e-9 for k in
                ('combination_operation_relative','actual_vs_thin_operation_relative'))
            and dual_gate(row['JVP_VJP']) and vector_gate(row['vector_Taylor']))


def compensation_gate(row):
    return (row.get('rank_P')==row.get('rank_A')==1560
            and row.get('compensation_sign')=='R_dot_gamma_EQUALS_MINUS_k'
            and finite(row.get('compensation_triangular_operation_error'))
            and row['compensation_triangular_operation_error']<=1e-10
            and row.get('QR_reassembly',float('inf'))<=1e-10
            and len(row.get('saved_A_three_original_checks',[]))>=3
            and max(row['saved_A_three_original_checks'])<=1e-10
            and row.get('Hhat_condition',float('inf'))<=1e10)


def audit_step_gate(row):
    return (all(finite(row.get(k)) and row[k]<=1e-10 for k in
                ('recovery_relative','schur_original_identity_operation_relative'))
            and row.get('slave_storage_max')==0
            and all(finite(row.get(k)) and row[k]<=1e-6 for k in
                    ('port_full_rhs_relative','port_operation_relative')))


def accepted_trial_gate(row):
    if (not row.get('hidden_step_real') or not row.get('actual_network_candidate')
        or row.get('linear_only_candidate') or row.get('hidden_change',0)<=0):
        return False
    keys=('old_loss','trial_loss','pred','old_delta_J','trial_delta_J','old_native')
    if not all(finite(row.get(k)) for k in keys):
        return False
    decrease=row['old_loss']-row['trial_loss']
    margin=max(1e-12,20*max(row['old_delta_J'],row['trial_delta_J']))
    audit=row['trial_audit']
    return (row['pred']>max(1e-12,100*row['old_delta_J']) and decrease>margin
            and decrease/row['pred']>=.1 and audit_step_gate(audit)
            and audit['native_relative']<=1.05*row['old_native'])


def frozen_network_gate(record):
    path=Path(record['path'])
    if file_hash(path)!=record['sha256']:
        return False
    with np.load(path,allow_pickle=False) as data:
        if data['hidden'].shape!=(8576,) or np.iscomplexobj(data['hidden']):
            return False
        if data['gamma'].shape!=(1560,) or data['port'].shape!=(40,) or data['z'].shape!=(18184,):
            return False
        values=data['network_parameters']
        if values.shape!=(11696,) or not np.array_equal(values[:8576],data['hidden']):
            return False
        weight=values[8576:11648].reshape(48,64);bias=values[11648:]
        head=np.empty((24,65),np.complex128)
        head[:,0]=bias[::2]+1j*bias[1::2]
        head[:,1:]=weight[::2]+1j*weight[1::2]
        if not np.array_equal(head.reshape(-1),data['gamma']):
            return False
        for key in ('hidden','gamma','port','z','network_parameters'):
            if not np.isfinite(data[key]).all() or array_hash(data[key])!=record[key+'_sha256']:
                return False
        return np.array_equal(data['port'],data['z'][-40:])


def check_v13(tangent,response,coupled,verify):
    a={x['name']:tangent_gate(x) for x in tangent['directions']}
    rounds=[]
    for row in coupled['rounds']:
        rounds.append(dict(head_compensation=compensation_gate(row['head_compensation']),
                           joint_directions={x['direction']:joint_gate(x) for x in row['joint_checks']}))
    trials=[accepted_trial_gate(x) for x in coupled['trials']]
    frozen=all(frozen_network_gate(x['state']) for x in tangent['states']+coupled['states'])
    fields={n:verified_field_gate(x) for n,x in verify['rows'].items()}
    errors=[]
    if list(a.values())!=[x['qualified'] for x in tangent['directions']]:
        errors.append('A.saved_direction_qualification')
    if trials!=[x['accepted'] for x in coupled['trials']] or sum(trials)!=coupled['accepted_C']:
        errors.append('C.acceptance_from_actual_numbers')
    if not frozen:
        errors.append('frozen_network_or_gamma_identity')
    for computed,saved in zip(rounds,coupled['rounds']):
        if not computed['head_compensation']:
            errors.append('C.head_compensation')
        if list(computed['joint_directions'].values())!=[x['qualified'] for x in saved['joint_checks']]:
            errors.append('C.saved_joint_qualification')
    for n,passed in fields.items():
        if passed!=(verify['rows'][n]['status']=='SAME_DISCRETE_QUALIFIED'):
            errors.append('D.'+n+'.saved_qualification')
    limits=dict(forward=400,JVP=48,VJP=24,FD_points=60,PA_builds=3,
                thin_decompositions=6,thin_RHS_columns=18,small_real_LS=3,original_audits=60)
    if any(verify['budget_counts'][k]>v for k,v in limits.items()) or verify['all_batch_equivalent_actions']>8000:
        errors.append('batch_operation_budget')
    if response['accepted_B']>1 or sum(trials)>3 or not verify['reference_only_after_solver_frozen']:
        errors.append('batch_dispatch_or_reference_barrier')
    origin=verify['rows']['INITIAL_V12_PHYSICAL'];new=verify['rows'].get('C_1_ACCEPTED')
    progress=False
    if new:
        rho=lambda x:max(x['audit'][k] for k in ('schur_relative','native_relative','port_full_rhs_relative'))
        progress=(rho(new)<=.5*rho(origin) and all(new['fields'][k]<=.5
                  and new['fields'][k]<=.75*origin['fields'][k]
                  for k in ('scattered_FE_L2_relative','scattered_scaled_curl_relative')))
    return dict(status='EVIDENCE_CONSISTENT' if not errors else 'RAW_EVIDENCE_MISMATCH',
        errors=errors,tangent_directions=a,coupled_rounds=rounds,accepted_C_from_raw=sum(trials),
        frozen_network_identity=frozen,same_discrete=fields,formal_micro_qualified=any(fields.values()),
        research_positive=bool(progress),outcome='RESEARCH_POSITIVE' if progress else
        'OBJECTIVE_ONLY_IMPROVEMENT' if coupled['final_loss']<coupled['initial_loss'] else 'BOUNDED_COUPLED_STEP_NEGATIVE',
        exact_VarPro_qualified=False,saved_success_labels_not_trusted=True)
