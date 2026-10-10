"""Independent saved V70/C5 consumers; no new assembly or numeric."""
import json
from pathlib import Path
import numpy as np
from src.runners.task042_shared import write_json
from src.solvers import assembly_tetra_scope as scope
from src.solvers.tetra_body_checkpoint import file_digest
from benchmarks.collect_exact_tetra import strict_reproduction


def compare_S():
    """Separate compare-only process. Old S cannot enter production BUILD."""
    scope.window.guard_worker_parent()
    from src.solvers import exact_tetra_scope as prior
    from src.solvers.exact_tetra_condensation import ExactRecovery
    from src.solvers.scattering_anchor import relative,save_arrays
    from src.solvers.scattering_anchor_checks import checked_arrays
    out=Path(__import__('os').environ['TASK042_V36_AUX_DIRECTORY'])
    new=scope.stage('BUILD');ref=checked_arrays(new['retained_action_witness'])
    old_record=prior.stage('PREPARE_C5');service=ExactRecovery(old_record['checkpoint'])
    if not np.array_equal(service.retained,ref['retained']):raise ValueError('old/new retained owner and MPC order')
    outputs=np.column_stack([service.matrix@ref['inputs'][:,i] for i in range(2)])
    m=828;errors=[]
    for i in range(2):
        delta=outputs[:,i]-ref['outputs'][:,i]
        errors.append(dict(full=relative(delta,outputs[:,i]),FE=relative(delta[:-m],outputs[:-m,i]),port=relative(delta[-m:],outputs[-m:,i])))
    raw=save_arrays(out/'two_old_S_reference_actions.npz',inputs=ref['inputs'],old_outputs=outputs,new_outputs=ref['outputs'],retained=service.retained)
    result=dict(status='COMPLETED',pass_gate=max(v for e in errors for v in e.values())<=1e-10,errors=errors,arrays=raw,
        old_S=old_record['checkpoint'],new_S=new['checkpoint'],source_role='COMPARE_ONLY_NOT_PRODUCTION',
        new_numeric_factors=0,new_complete_solves=0,old_full_K_reads=0,old_recovery_chunk_reads=0)
    write_json(out/'S_pair.json',result)
    if not result['pass_gate']:raise ValueError('independent old/new S action gate')
    write_json(scope.window.TMP/'compare_S_receipt.json',dict(path=str(out/'S_pair.json'),sha256=file_digest(out/'S_pair.json')))
    print(json.dumps(dict(status='TWO_OLD_NEW_S_ACTIONS_PASS',errors=errors)))


def verify(folder,journal):
    from src.solvers import exact_tetra_scope as prior
    from src.solvers.tetra_polynomial_difference import comparison
    from src.solvers.independent_tetra_fields import selected_points
    from benchmarks.collect_frozen_local_h import saved_original
    from benchmarks.check_independent_tetra import saved_pair
    inventory=scope.verification_inventory_for('VERIFY_COST')
    if inventory is None or journal.source_state.get('verification_inventory',{}).get('sha256')!=file_digest(inventory):raise ValueError('V70 frozen unique consumer inventory')
    frozen=json.loads(inventory.read_text());r=scope.stage('SOLVE')
    if frozen['states']['SOLVE']['array_sha256']!=r['arrays']['sha256']:raise ValueError('V70 frozen complete field identity')
    own=folder/'new';own.mkdir(exist_ok=True)
    check=saved_original(r,own,journal,body_q=15)
    # Reference coefficients are opened only after all new candidates freeze.
    parent=prior.stage('C5');pair=comparison(parent,r,folder/'C5_V70',journal,coefficient_first=True)
    independent=saved_pair(pair,parent,r,expected_points=selected_points(r['physical']))
    if not independent['published_gate_matches_recalculation']:raise ValueError('V70 saved score consistency')
    strict=strict_reproduction(pair)
    result=dict(status='COMPLETED',pass_gate=check['pass_gate'] and strict['pass_gate'] and r['equation_pass'],
        checks={'SOLVE':check},comparisons={'C5_V70':pair},strict_scores={'C5_V70':strict},independent_pairs={'C5_V70':independent},
        frozen_inventory=dict(path=str(inventory),sha256=file_digest(inventory)),source=journal.source_state,
        timings=journal.timings,calls=journal.calls,new_numeric_factors=0,new_complete_solves=0,
        continuum_accuracy=False,target_qualified=False,NN20=False)
    write_json(folder/'verification_scientific_result.json',result);return result


if __name__=='__main__':compare_S()
