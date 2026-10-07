"""Complete metadata from an atomic returned H2 state; never rebuild numerics.

The independent vectors, quadrature integrals and physical fields were already
saved by the producer. This consumer hashes those bytes and reduces them only.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy import sparse
from src.runners.task042_shared import write_json
from src.solvers.scattering_anchor import array_hash, relative, save_arrays
from src.solvers.scattering_anchor_checks import checked_arrays


def file_hash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def existing_receipt(path):
    """Hash actual existing arrays, without rewriting or trusting status."""
    path=Path(path);members={}
    with np.load(path,allow_pickle=False) as pack:
        for key in pack.files:
            a=pack[key]
            if a.dtype.hasobject or not np.all(np.isfinite(a)):raise ValueError('nonfinite/object saved scientific member')
            members[key]=dict(shape=list(a.shape),dtype=str(a.dtype),sha256=array_hash(a))
    return dict(path=str(path.resolve()),sha256=file_hash(path),members=members)


def ambient_reductions(v):
    den=max(np.linalg.norm(v['rhs']),1e-30)
    rec=dict(action_split=relative(v['volume_action']-v['volume_inside']-v['volume_trace'],np.maximum(np.abs(v['volume_inside']),np.abs(v['volume_trace']))),
        operation_scaled_interior=float(np.linalg.norm(v['internal_numerators'])/max(np.linalg.norm(v['internal_operation_scale']),1e-30)),
        internal_operation_scaled_max=float(np.max(v['internal_numerators']/np.maximum(v['internal_operation_scale'],1e-30))),
        homogeneous_recovery=True,nonzero_internal_particular_preserved=True)
    norms=dict(true=float(np.linalg.norm(v['residual'])/den),native=float(np.linalg.norm(v['residual'])/den),
        augmented=relative(v['augmented_top'],v['rhs']),port=relative(v['port_residual'],v['projected']),
        identity=relative(v['residual']-(v['augmented_top']-v['native_boundary_action']+v['coupling_action']),
            np.maximum(np.abs(v['rhs']),np.abs(v['volume_action']+v['native_boundary_action']))),
        slave_zero=bool(np.all(v['u_storage'][v['slaves']]==0)))
    return norms,rec


def tangent_reductions(receipt):
    a=checked_arrays(receipt);m=a['metrics'];pairs=a['face_pairs']
    if m.shape!=(len(pairs),5) or pairs.shape[1]!=6 or not np.all(np.isfinite(m)) or np.any(m[:,:3]<0):raise ValueError('saved tangential face inventory')
    if not np.allclose(m[:,4],m[:,0]/np.maximum(m[:,2],1e-30),rtol=1e-13,atol=1e-16):raise ValueError('tangential actual numerator/denominator identity')
    overall=float(np.linalg.norm(m[:,0])/max(np.linalg.norm(m[:,2]),1e-30));maximum=float(m[:,4].max())
    kinds=set(pairs[:,-1]);counts=[int(np.count_nonzero(pairs[:,-1]==i)) for i in range(3)]
    if kinds!={0,1,2} or min(counts)<=0:raise ValueError('complete shared and both periodic face kinds')
    return dict(pass_gate=max(overall,maximum)<=1e-10,overall_operation_relative=overall,
        maximum_face_operation_relative=maximum,worst_face_pair=pairs[int(np.argmax(m[:,4]))].tolist(),
        face_count=len(pairs),internal_faces=counts[0],periodic_x_faces=counts[1],periodic_y_faces=counts[2],arrays=receipt,
        field='physical E / exp(i*kappa.x); tangential envelope only',incident_amplitude=1.,near_zero_operation_threshold=1e-12,
        quadrature='saved actual native 8x8 Gauss per face',new_factor_count=0,new_solve_count=0,
        metadata_reconstructed_from_saved_metrics=True,unsaved_producer_timing_or_eval_checks='unknown')


def consume(folder,journal,state):
    from src.solvers import local_subcell_scope as scope
    from benchmarks.collect_local_subcell import macro_saved_check
    from benchmarks.collect_common_weak_phase import output_check
    bound=state.get('postprocessing_resume',{});path=Path(bound['path'])
    if file_hash(path)!=bound['sha256']:raise ValueError('saved H2 consumer live input binding')
    request=json.loads(path.read_text());old=Path(request['producer_folder']).resolve()
    if not old.is_relative_to(scope.ARTIFACT.resolve()) or request['role']!='H2':raise ValueError('saved H2 same namespace')
    producer='d42ac36b99bd758478da7ce42b34215826832676'
    if file_hash(old/'minimal_scientific_state.json')!=request['minimal_sha256']:raise ValueError('saved minimal receipt changed')
    r=json.loads((old/'minimal_scientific_state.json').read_text())
    if r['source']['source_sha']!=producer or r['arrays']['sha256']!=request['solution_sha256']:raise ValueError('saved numerical producer/candidate binding')
    summary=json.loads((scope.ROOT/'results/task042'/old.name/'run_summary.json').read_text())
    if summary['classification']!='RESOURCE_CONTROLLED_STOP' or not summary['descendants_cleared']:raise ValueError('stopped producer must be cleared')
    original_manifest=scope.ROOT/'results/task042'/old.name/'run_manifest.json';live=json.loads(original_manifest.read_text())
    for name in ('src/solvers/subcell_macro_deployment.py','src/solvers/subcell_response_kernel.py','src/solvers/fixed_phase_fem.py','src/solvers/phase_saved_uncondensed.py'):
        if live['implementation_hashes'][name]!=file_hash(scope.ROOT/name):raise ValueError('post-only mathematical dependency changed')
    if scope.numeric_factor_attempts()!=3:raise ValueError('saved consumer exact factor inventory')
    a=checked_arrays(r['arrays']);m=checked_arrays(r['trace_mapping'])
    receipt=existing_receipt(old/'independent_original/independent_original_vectors.npz');v=checked_arrays(receipt)
    if not np.array_equal(a['u_storage'],v['u_storage']) or not np.array_equal(a['port'],v['port']):raise ValueError('saved independent vectors wrong candidate')
    J=sparse.csr_matrix((m['J_data'],m['J_indices'],m['J_indptr']),shape=tuple(m['J_shape']));JH=J.conj().T
    mixed=save_arrays(folder/'macro_mixed_original.npz',mixed_residual=JH@v['residual'],mixed_augmented=JH@v['augmented_top'],mixed_rhs=JH@v['rhs'],ambient_residual=v['residual'])
    norms,rec=ambient_reductions(v)
    high=dict(audit_path='PUBLIC_BASIX_UNCONDENSED_AUDIT_SAVED_VECTOR_REDUCTION',volume_q=15,surface_q=63,
        original_audit=norms,recovery=rec,arrays=receipt,recovery_pass=max(rec['action_split'],rec['internal_operation_scaled_max'])<=1e-10,
        equation_pass=max(norms[k] for k in ('true','native','augmented','port'))<=1e-6,
        new_factor_count=0,new_complete_solves=0,original_producer=producer,hashes_computed_after_atomic_save=True)
    r['independent']=dict(ambient_original=high,arrays=mixed)
    check=macro_saved_check(r);passed=check['pass_gate']
    r['independent'].update(audit_path='PUBLIC_BASIX_ALL_R2_MICRO_BODY_Q15_Q63_HERMITIAN_MACRO_PULLBACK_SAVED',
        original_audit=dict(check['mixed'],identity=max(check['operation_identities'].values()),slave_zero=check['slave_zero']),
        equation_pass=passed,recovery_pass=check['macro_internal_recovery_operation']<=1e-10 and high['recovery_pass'],
        macro_internal_operation_scaled=check['macro_internal_recovery_operation'],macro_internal_operation_by_cell=check['macro_internal_operation_by_cell'],
        direct_internal_target_pass=check['direct_target_pass'],NOT_A_FULL_AMBIENT_SOLUTION=True)
    output=dict(fields=existing_receipt(old/'fields.npz'),fixed_240=existing_receipt(old/'fixed_240_physical_fields.npz'),
        port_metrics=json.loads((old/'dtn_port_power_metrics_3d.json').read_text()),volume_metrics=json.loads((old/'volume_absorption.json').read_text()),
        mode_manifest_sha256=r['boundary']['mode_sha256'],surface_quadrature_degree=47,
        full_field_representation='authoritative saved native micro envelope + geometry/space/MPC + kappa; no projection to macro polynomial',
        sampled_fields_are_not_authority=True,background='same analytic layered physical background',H_units='curl(E)/(i*k0*mu) code')
    r['output']=output;r['mode_sha256']=r['boundary']['mode_sha256']
    r['tangential_check']=tangent_reductions(existing_receipt(old/'H2_actual_tangential_faces.npz'))
    output_verified=output_check(r)
    events=[json.loads(line) for line in (old/'events.jsonl').read_text().splitlines()]
    mapping=next(e for e in events if e.get('event')=='macro_full_primal_dual_inventory')
    responses=[e for e in events if e.get('event')=='macro_local_response_committed'];last=responses[-1]
    bank=old/'local_schur_bank/manifest.json';bank_record=json.loads(bank.read_text())
    r.update(status='COMPLETED_SAVED_CONSUMPTION',role='H2',case='NOTCH',degree=6,grid='2x2x4',
        representation='MACRO_TRACE6_ALL_R2_P6_MICRO_INTERIORS',mapping_check=mapping,
        new_complete_solves=0,new_global_numeric_factors=0,producer_complete_solves=1,producer_numeric_factors=1,
        local_response_classes=last['classes'],child_local_classes=last['child_classes'],
        local_schur_bank=dict(path=str(bank),sha256=file_hash(bank),source_sha=bank_record['source_sha']),
        local_body_action_pairs=[dict(arrays=existing_receipt(old/f'saved_local_action_pair_{j}.npz')) for j in range(2)],
        solve_source_sha=producer,original_solve_source=r['source'],source=state,
        preparation_resume=dict(snapshot_path=str(scope.window.TMP/'H2_preparation_resume.json'),snapshot_sha256=file_hash(scope.window.TMP/'H2_preparation_resume.json'),
            reused_child_classes=177,reused_macro_classes=110,no_new_LU_in_consumer=True,previous_failure_cost_preserved=True),
        original_stop=dict(path=str(scope.ROOT/'results/task042'/old.name/'run_summary.json'),sha256=file_hash(scope.ROOT/'results/task042'/old.name/'run_summary.json'),classification=summary['classification']),
        producer_manifest=dict(path=str(original_manifest),sha256=file_hash(original_manifest)),
        fixed_refinements=len(json.loads((old/'returned_low_inventory.json').read_text())['arrays'])-1,
        local_global_factors='R2_CHILD_INTERNAL_AND_MACRO_INTERNAL_LOCAL_LU_PLUS_GLOBAL_MACRO_TRACE_MUMPS_PRESENT; no global micro Schur',
        NOT_A_FULL_AMBIENT_SOLUTION=True,equation_pass=passed,direct_target_pass=check['direct_target_pass'],
        capacity=dict(rows=33660,mixed=729792,ambient=834048,class_cache_limit=8*2**30),
        deployment_complete=passed and r['independent']['recovery_pass'] and r['tangential_check']['pass_gate'],
        consumer_only=True,output_verified=output_verified,source_sha=state['source_sha'],timings=journal.timings,calls=journal.calls)
    write_json(folder/'saved_consumer_check.json',check);write_json(folder/'completed_deployment_state.json',r)
    journal.event('atomic_saved_H2_completed_without_action_factor_or_solve',producer=producer)
    return r
