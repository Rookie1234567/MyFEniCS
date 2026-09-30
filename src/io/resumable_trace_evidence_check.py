"""Independent raw V17 evidence checks; never advances a numerical solve."""
import math
from pathlib import Path

import numpy as np

from src.io.augmented_trace_evidence_check import equation, image, projected
from src.io.actual_loss_block_descent_check import verified_field_gate
from src.solvers.neural_fe_action_packet import array_hash, file_hash


def resume_pair(row):
    p=row['resume_pair'];w=row['algebra_witness']
    return bool(projected(row['operator_checks']) and image(row['original_image'])
        and p['short_steps']==32 and p['independent_reader']
        and p['production_progress_unchanged'] and not p['reference_read']
        and all(math.isfinite(d['operation_relative']) and d['operation_relative']<=1e-12
                for d in p['full_GK_differences'].values())
        and p['z']['operation_relative']<=1e-12
        and p['original_action']['operation_relative']<=1e-12
        and w['known_z_relative']<=1e-8 and w['manufactured_residual_relative']<=1e-8
        and w['homogeneous_recovery_operation_relative']<=1e-10
        and w['projected_identity']['operation_relative']<=1e-8
        and w['physical_rhs_unchanged'] and not w['iterative_manufactured_solve'] and not w['reference_read'])


def field_gate(row,reference_pass):
    return bool(reference_pass and equation(row['audit']) and verified_field_gate(row)
        and row['audit'].get('independent_DOLFINx_total_native_relative',math.inf)<=1e-6
        and all(math.isfinite(v) and 0<=v<=1e-4 for v in row['fields'].values()))


def caps(ledger,budget):
    if ledger.get('active') or not ledger['closed']:return False
    if not (ledger['actions_upper']<=56000 and ledger['audits_upper']<=420
            and ledger['new_A_columns']<=6196 and ledger['image_QR']<=2
            and ledger['field_states']<=12 and ledger['reentries']<=3
            and ledger['cooldown_seconds']<=1800 and len(ledger['repairs'])<=4):return False
    return all(r['wall_seconds']<=budget['uniform_route_wall_seconds']
               and r['actions_upper']<=24000 and r['new_updates']<=8192
               and r['reentries']<=2 and r['correction_restarts']<=1
               for r in ledger['routes'].values())


def frozen_state(source,bnorm,basis=None):
    record=source['state'];path=Path(record['path'])
    if file_hash(path)!=record['sha256']:raise ValueError('state file hash differs')
    with np.load(path,allow_pickle=False) as stream:a={k:np.array(stream[k]) for k in stream.files}
    for k,v in a.items():
        if not np.isfinite(v).all():raise ValueError('nonfinite raw state')
        if k+'_sha256' in record and array_hash(v)!=record[k+'_sha256']:
            raise ValueError(k+' raw hash differs')
    if a['z'].shape!=(18184,) or a['trace'].shape!=(18144,) or a['port'].shape!=(40,):
        raise ValueError('canonical trace/40 ports shape differs')
    if not np.array_equal(a['z'],np.r_[a['trace'],a['port']]):raise ValueError('z trace/port composition')
    decoded=None
    if basis is not None and 'v' in a and 'c' in a:
        if a['c'].shape!=(3098,):raise ValueError('matched 3098 coefficient capacity')
        value=a['v']+basis[0]@a['c'][:1560]+basis[1]@a['c'][1560:]
        decoded=float(np.linalg.norm(value-a['trace'])/max(np.linalg.norm(a['trace']),1e-300))
        if decoded>1e-10:raise ValueError('saved trace is not v+Qc')
    rho=float(np.linalg.norm(a['residual'])/bnorm) if 'residual' in a else None
    Phi=float(np.vdot(a['residual'],a['residual']).real/(2*bnorm**2)) if 'residual' in a else None
    audit=source.get('audit')
    if audit and rho is not None and abs(rho-audit['schur_relative'])>1e-12:
        raise ValueError('raw residual versus saved Schur')
    if source.get('Phi') is not None and abs(Phi-source['Phi'])>1e-12:
        raise ValueError('raw residual versus Phi')
    if source.get('original_residual_identity_relative',0)>1e-8:
        raise ValueError('projected/original identity')
    return dict(Schur_raw=rho,Phi_raw=Phi,decoded_trace_relative=decoded,
                raw_vectors_finite=True,actual_z_composition=True)


def check_v17(pre,ledger,budget,verify):
    errors=[];qualified={};states={}
    packet=pre['operator_packet']
    if file_hash(packet['path'])!=packet['sha256']:errors.append('action_packet_hash')
    with np.load(packet['path'],allow_pickle=False) as stream:
        bnorm=float(np.linalg.norm(stream['b']));master=array_hash(stream['masters'])
    interfaces={f:resume_pair(p) for f,p in pre['libraries'].items()}
    if not all(interfaces.values()):errors.append('real_resume_interface')
    if pre['action_counts']['S']+pre['action_counts']['SH']>400:errors.append('R1_action_cap')
    if not caps(ledger,budget):errors.append('campaign_cap_or_freeze')
    if not verify['reference_native_pass'] or verify['reference_audit']['independent_DOLFINx_total_native_relative']>1e-10:
        errors.append('reference_native')
    if verify['reference_feedback_to_solver'] or not verify['no_new_solve'] or not verify['no_new_LU']:
        errors.append('reference_boundary')
    if verify['states_read']!=len(verify['rows']) or len(verify['rows'])>12:errors.append('field_inventory')
    for family,info in pre['libraries'].items():
        im=info['original_image'];bi=im['basis_identity']
        if bi['canonical_master_sha256']!=master or bi['complement']['take_columns']!=1538:
            errors.append(family+'.canonical_order_or_capacity')
        for item in (bi['G0'],bi['complement'],im['U'],im['R']):
            if file_hash(item['path'])!=item['sha256']:errors.append(family+'.basis_image_hash')
        basis=[np.load(bi['G0']['path'],mmap_mode='r'),np.load(bi['complement']['path'],mmap_mode='r')[:,:1538]]
        for name,source in verify['state_sources'].items():
            if family not in name:continue
            try:states[name]=frozen_state(source,bnorm,basis if 'GMRES' not in name else None)
            except (ValueError,KeyError) as error:errors.append(name+'.'+str(error))
        del basis
    for name,row in verify['rows'].items():
        qualified[name]=field_gate(row,verify['reference_native_pass'])
        if qualified[name]!=(row['status']=='SAME_DISCRETE_QUALIFIED'):errors.append(name+'.field_status')
        if equation(row['audit'])!=(row['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS'):
            errors.append(name+'.equation_status')
    return dict(status='EVIDENCE_CONSISTENT' if not errors else 'RAW_MISMATCH',mismatches=errors,
                recovered_interfaces=interfaces,raw_state_checks=states,strict_same_discrete=qualified,
                strict_qualified_states=sum(qualified.values()),no_saved_status_trusted=True,
                new_equation_solves_in_checker=0,no_hidden_training_claimed=True)
