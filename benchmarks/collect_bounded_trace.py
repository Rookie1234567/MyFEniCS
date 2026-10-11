"""Independent frozen V71 arrays and strict V70 reference consumer."""
import json
from pathlib import Path
from src.runners.task042_shared import write_json
from src.solvers import bounded_trace_scope as scope
from src.solvers.tetra_body_checkpoint import file_digest


def verify(folder,journal):
    from src.solvers import assembly_tetra_scope as prior
    from src.solvers.tetra_polynomial_difference import comparison
    from src.solvers.independent_tetra_fields import selected_points
    from benchmarks.collect_frozen_local_h import saved_original
    from benchmarks.check_independent_tetra import saved_pair
    from benchmarks.collect_exact_tetra import strict_reproduction
    frozen=scope.verification_inventory_for('VERIFY_COST')
    if frozen is None:
        return dict(status='NOT_RUN',pass_gate=False,reason='no frozen returned candidate; healthy O/P and blocked inventory retained',
                    new_complete_solves=0,new_numeric_factors=0)
    freeze=json.loads(frozen.read_text());r=scope.stage('ITERATE')
    if freeze['retained']['sha256']!=r['retained_returned']['sha256']:raise ValueError('V71 frozen retained identity')
    own=folder/'new';own.mkdir(exist_ok=True)
    from src.solvers.bounded_trace_study import action_charge
    check=action_charge('V_saved_public_original',lambda:saved_original(r,own,journal,body_q=15))
    parent=prior.stage('SOLVE')
    pair=comparison(parent,r,folder/'V70_V71',journal,coefficient_first=True)
    independent=saved_pair(pair,parent,r,expected_points=selected_points(r['physical']))
    strict=strict_reproduction(pair)
    if not independent['published_gate_matches_recalculation']:raise ValueError('V71 saved independent comparison decision')
    result=dict(status='COMPLETED',pass_gate=check['pass_gate'] and strict['pass_gate'] and r['scientific_solve_pass'],
        independent_original=check,comparison=pair,strict_scores=strict,independent_pair=independent,
        frozen_inventory=dict(path=str(frozen),sha256=file_digest(frozen)),source=journal.source_state,
        timings=journal.timings,calls=journal.calls,new_numeric_factors=0,new_complete_solves=0,
        continuum_accuracy=False,target_qualified=False,NN20=False)
    write_json(folder/'verification_scientific_result.json',result);return result
