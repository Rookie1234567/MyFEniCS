"""Independent saved C5/M5 consumption; no global assembly or numeric."""
import json
from pathlib import Path

import numpy as np

from src.runners.task042_shared import write_json
from src.solvers import exact_tetra_scope as scope
from src.solvers.tetra_body_checkpoint import file_digest
from benchmarks.collect_frozen_local_h import saved_original,first_normalization,project_old_field


def strict_reproduction(pair):
    """Recompute the stricter same-discretization limits from actual metrics."""
    names={kind+'_'+part for part in ('total','scattered') for kind in ('E','H','curl')}
    if set(pair.get('fields',{}))!=names or set(pair.get('selected',{}))!=names:
        return dict(inventory_complete=False,pass_gate=False)
    values=[r['relative'] for r in pair['fields'].values()]+list(pair['selected'].values())
    finite=all(np.isfinite(x) and x>=0 for x in values)
    result=dict(inventory_complete=True,complete_fields_and_points=finite and max(values)<=1e-6,
        complex_channels=np.isfinite(pair['modes']['outgoing_amplitude_at_boundary_relative']) and pair['modes']['outgoing_amplitude_at_boundary_relative']<=1e-6,
        powers=max(pair['power_differences'].values())<=1e-8,
        per_mode_power=pair['modes']['mode_power_max_absolute']<=1e-9,
        energy=max(pair['energies'])<=1e-5,
        quadrature=pair['quadrature_operation_scaled']<=1e-10)
    result['pass_gate']=all(result.values());return result


def verify(folder,journal):
    from src.solvers import durable_l5_scope as L5
    from src.solvers.tetra_polynomial_difference import comparison
    from src.solvers.independent_tetra_fields import selected_points
    from benchmarks.check_independent_tetra import saved_pair
    inventory=scope.verification_inventory_for('VERIFY_COST')
    if inventory is None or journal.source_state.get('verification_inventory',{}).get('sha256')!=file_digest(inventory):
        raise ValueError('V69 live frozen consumer inventory')
    frozen=json.loads(inventory.read_text());parent=L5.stage('SOLVE_COMPLETE')
    for role,item in frozen['states'].items():
        if scope.stage(role)['arrays']['sha256']!=item['array_sha256']:raise ValueError('V69 frozen returned coefficients')
    checks={};pairs={};scores={};independent={};prior=None
    if frozen['phase']=='C5_ONLY':
        candidate=scope.stage('C5');own=folder/'C5';own.mkdir(exist_ok=True)
        checks['C5']=saved_original(candidate,own,journal,body_q=15)
        pair=comparison(parent,candidate,folder/'L5_C5',journal)
        check=saved_pair(pair,parent,candidate,expected_points=selected_points(candidate['physical']))
        if not check['published_gate_matches_recalculation']:raise ValueError('V69 independent reproduction score')
        pairs['L5_C5']=pair;independent['L5_C5']=check;scores['L5_C5']=strict_reproduction(pair)
        passed=scores['L5_C5']['pass_gate'] and checks['C5']['pass_gate'] and candidate['equation_pass']
        decision=dict(backend='EXACT_CONDENSED' if passed else 'FULL_UNCONDENSED',
            reason='strict same-discretization reproduction and original audit' if passed else 'C5 strict reproduction not established',
            C5_array_sha256=candidate['arrays']['sha256'],comparison=scores['L5_C5'],checks=checks['C5']['pass_gate'],
            frozen_inventory=dict(path=str(inventory),sha256=file_digest(inventory)))
        write_json(scope.window.TMP/'M5_backend.json',decision)
        status='C5_REPRODUCTION_COMPLETE'
    else:
        prior_path=scope.window.TMP/'C5_consumer_receipt.json'
        if prior_path.exists():
            r=json.loads(prior_path.read_text());p=Path(r['path'])
            if file_digest(p)!=r['sha256']:raise ValueError('C5 immutable consumer receipt')
            prior=json.loads(p.read_text());checks.update(prior['checks']);pairs.update(prior['comparisons']);scores.update(prior['strict_scores'])
        if 'M5' in frozen['states']:
            candidate=scope.stage('M5');own=folder/'M5';own.mkdir(exist_ok=True)
            checks['M5']=saved_original(candidate,own,journal,body_q=15)
            projection=folder/'L5_all1188';projection.mkdir(exist_ok=True)
            projected=project_old_field(parent,candidate,projection,journal)
            pair=comparison(projected,candidate,folder/'L5_M5',journal)
            check=saved_pair(pair,projected,candidate,expected_points=selected_points(candidate['physical']))
            if not check['published_gate_matches_recalculation']:raise ValueError('V69 independent all1188 saved score')
            pairs['L5_M5']=pair;independent['L5_M5']=check
            scores['L5_M5']=dict(second_denominator_pass=pair['pass_gate'],first_denominator=first_normalization(pair,parent,label='L5'))
        status='COMPLETED'
    result=dict(status=status,checks=checks,comparisons=pairs,strict_scores=scores,independent_pairs=independent,
        source=journal.source_state,timings=journal.timings,calls=journal.calls,
        frozen_inventory=dict(path=str(inventory),sha256=file_digest(inventory),
            C5_array_sha256=frozen['states'].get('C5',{}).get('array_sha256')),
        new_numeric_factors=0,new_complete_solves=0,continuum_accuracy=False,target_qualified=False,NN20=False)
    write_json(folder/'verification_scientific_result.json',result);return result
