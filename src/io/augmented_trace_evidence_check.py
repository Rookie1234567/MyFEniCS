"""V16 raw-number/hash checks after the numerical and reference queues freeze."""
import math
from pathlib import Path
import numpy as np
from src.io.actual_loss_block_descent_check import verified_field_gate
from src.solvers.neural_fe_action_packet import array_hash, file_hash


def equation(a):
    return all(math.isfinite(a.get(k,math.inf)) and 0<=a[k]<=1e-6 for k in
        ('schur_relative','native_relative','augmented_relative','original_total_augmented_relative',
         'port_full_rhs_relative','port_operation_relative')) and a.get('recovery_relative',math.inf)<=1e-10 \
         and a.get('schur_original_identity_operation_relative',math.inf)<=1e-10 and a.get('slave_storage_max')==0


def projected(c):
    return all(t['operation_relative']<=1e-10 for t in c['dot_tests']) and \
        all(t['operation_relative']<=1e-10 for t in c['idempotence'].values()) and \
        max(c['annihilation'].values())<=1e-10 and c['original_residual_identity_relative']<=1e-8


def image(row):
    return row['rank']==row['columns']==3098 and row['relative_rank_threshold']==1e-12 and \
        max(row['Q_orthogonality'],row['U_orthogonality'],row['A_QR_reconstruction'])<=1e-10 and \
        all(p['operation_relative']<=1e-10 for p in row['original_pairings']) and \
        row['bar_checks']['Hhat_condition']<=1e10 and max(row['bar_checks']['Hhat_solve_operation_relative'])<=1e-12 and \
        all(p['operation_relative']<=1e-10 for p in row['bar_checks']['single_SH_vs_legacy_two_SH'])


def check_v16(pre, routes, verify):
    problems=[];recomputed={};interfaces={};qualified={};missing_evidence=[]
    p=pre['operator_packet']
    if file_hash(p['path'])!=p['sha256']:problems.append('action_packet_hash')
    with np.load(p['path'],allow_pickle=False) as saved:bnorm=np.linalg.norm(saved['b']);master=array_hash(saved['masters'])
    w=pre['algebra_witness'];interfaces['ZERO']=projected(pre['empty_Q_checks'])
    interfaces['GPOLY']=image(pre['augmented_setup']) and projected(pre['augmented_checks']) and \
        w['known_z_relative']<=1e-8 and w['manufactured_residual_relative']<=1e-8 and \
        w['homogeneous_recovery_operation_relative']<=1e-10 and w['projected_identity']['operation_relative']<=1e-8 and \
        w['physical_rhs_unchanged'] and not w['iterative_manufactured_solve'] and not w['reference_read']
    for name,row in routes.items():
        if 'final' not in row:continue
        setup=row['image_setup'];identity=setup['basis_identity'];r=setup['columns']
        if name=='GNN':
            if setup.get('projected_checks') is None:
                interfaces[name]=None
                missing_evidence.append('GNN M/MH dot/projector numbers lost with killed worker; image raw qualified='+str(image(setup)))
                if not image(setup):problems.append('GNN.image_setup')
            else:interfaces[name]=image(setup) and projected(setup['projected_checks'])
        if r:
            for item in (identity['G0'],identity['complement'],setup['U'],setup['R']):
                if file_hash(item['path'])!=item['sha256']:problems.append(name+'.basis_or_image_hash')
            if identity['complement']['take_columns']!=1538 or identity['canonical_master_sha256']!=master:problems.append(name+'.matched_capacity_or_order')
            blocks=[np.load(identity['G0']['path'],mmap_mode='r'),np.load(identity['complement']['path'],mmap_mode='r')[:,:1538]]
        else:blocks=[]
        for cp in row['checkpoints']:
            s=cp['state'];path=Path(s['path'])
            if file_hash(path)!=s['sha256']:problems.append(name+'.state_file_hash');continue
            with np.load(path,allow_pickle=False) as a:
                for k in a.files:
                    if k+'_sha256' in s and array_hash(a[k])!=s[k+'_sha256']:problems.append(name+'.'+k+'_hash')
                    if not np.isfinite(a[k]).all():problems.append(name+'.nonfinite_state')
                if a['z'].shape!=(18184,) or a['trace'].shape!=(18144,) or a['port'].shape!=(40,) or a['c'].shape!=(r,) or not np.array_equal(a['z'],np.r_[a['trace'],a['port']]):problems.append(name+'.state_inventory')
                decoded=np.array(a['v'])
                if r:decoded+=blocks[0]@a['c'][:1560]+blocks[1]@a['c'][1560:]
                delta=float(np.linalg.norm(decoded-a['trace'])/max(np.linalg.norm(a['trace']),1e-300))
                rho=float(np.linalg.norm(a['residual'])/bnorm);Phi=float(np.vdot(a['residual'],a['residual']).real/(2*bnorm**2))
                if delta>1e-10 or abs(rho-cp['audit']['schur_relative'])>1e-12 or abs(Phi-cp['Phi'])>1e-12:problems.append(name+'.raw_trace_or_residual')
                if int(a['iteration'])!=cp['iteration']:problems.append(name+'.iteration_identity')
                if cp['iteration'] and int(a['GK_iteration'])!=cp['iteration']:problems.append(name+'.GK_snapshot_identity')
            if equation(cp['audit'])!=(cp['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS'):problems.append(name+'.equation_status')
            if cp['original_residual_identity_relative']>1e-8:problems.append(name+'.projected_original_identity')
            if cp['resumable_claimed']:problems.append(name+'.unsupported_resume_claim')
            recomputed[name+'-'+str(cp['iteration'])+('-FINAL' if cp['final'] else '')]=dict(Schur=rho,Phi=Phi,decoded_trace_relative=delta)
        del blocks
        if row['iteration_count']>4096 or row['iteration_equivalent_actions']>13000 or row['route_accounted_wall_seconds']>row['uniform_wall_budget']['uniform_route_wall_seconds']:problems.append(name+'.route_budget')
        if not row['independent_y_zero_start'] or not row['no_other_route_warm_start'] or not row['queue_frozen'] or row['reference_arrays_read']:problems.append(name+'.data_boundary')
    reference_ok=verify['reference_audit']['native_qualified'] and verify['reference_audit']['audit']['independent_DOLFINx_total_native_relative']<=1e-10
    for name,row in verify['rows'].items():
        good=bool(reference_ok and verified_field_gate(row) and equation(row['audit']) and \
             row['audit']['independent_DOLFINx_total_native_relative']<=1e-6 and \
             all(row['fields'][k]<=1e-4 for k in ('scattered_FE_L2_relative','scattered_scaled_curl_relative')))
        qualified[name]=good
        if good!=(row['status']=='SAME_DISCRETE_QUALIFIED'):problems.append(name+'.full_field_status')
    if not verify['reference_only_after_solver_frozen'] or verify['reference_feedback_to_solver']:problems.append('reference_barrier')
    if verify['all_batch_equivalent_actions']>50000 or verify['states_read']>10:problems.append('batch_caps')
    if verify['budget_counts']['new_A_columns']>6196 or verify['budget_counts']['image_QR']>2 or verify['budget_counts']['original_audits']>240:problems.append('setup_audit_caps')
    return dict(status=('EVIDENCE_CONSISTENT_RESOURCE_PARTIAL' if missing_evidence else 'EVIDENCE_CONSISTENT') if not problems else 'RAW_MISMATCH',mismatches=problems,missing_evidence=missing_evidence,
                original_and_projected_interfaces=interfaces,raw_residual_and_decoder_recomputed=recomputed,
                strict_same_discrete=qualified,strict_qualified_states=sum(qualified.values()),
                no_saved_status_trusted=True,no_hidden_training_claimed=True)
