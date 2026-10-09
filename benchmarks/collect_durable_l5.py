"""Two frozen original-field comparisons; no matrix/factor or PDE replay."""
import json
from src.runners.task042_shared import write_json
from src.solvers import durable_l5_scope as scope
from benchmarks.collect_frozen_local_h import saved_original,first_normalization
from benchmarks.collect_independent_tetra import digest


def verify(folder,journal):
    from src.solvers.tetra_polynomial_difference import comparison
    from src.solvers.independent_tetra_fields import selected_points
    from benchmarks.check_independent_tetra import saved_pair
    from src.solvers import frozen_local_h_scope as L4,p6_completion_scope as P6
    path=scope.verification_inventory_for('VERIFY_COST')
    if path is None or journal.source_state.get('verification_inventory',{}).get('sha256')!=digest(path):raise ValueError('V68 frozen inventory')
    frozen=json.loads(path.read_text());r=scope.stage('SOLVE_COMPLETE')
    if r['arrays']['sha256']!=frozen['states']['L5']['array_sha256']:raise ValueError('V68 frozen coefficients')
    own=folder/'L5';own.mkdir(exist_ok=True)
    checks={'L5':saved_original(r,own,journal,body_q=15)}
    pairs={};independent={};normalizations={}
    for label,parent in [('L4F',L4.stage('SOLVE_COMPLETE')),('P6',P6.stage('SOLVE_COMPLETE'))]:
        key=label+'_L5';pair=comparison(parent,r,folder/key,journal)
        check=saved_pair(pair,parent,r,expected_points=selected_points(r['physical']))
        if not check['published_gate_matches_recalculation']:raise ValueError('V68 independent saved score')
        alt=first_normalization(pair,parent,label=label)
        write_json(folder/(key+'_first_denominator.json'),alt)
        pairs[key]=pair;independent[key]=check;normalizations[key]=alt
        write_json(folder/'saved_pair_progress.json',dict(comparisons=pairs,independent=independent,first_normalizations=normalizations))
    result=dict(status='COMPLETED',checks=checks,comparisons=pairs,independent_pairs=independent,first_normalizations=normalizations,
        returned_states=['L5'],new_numeric_factors=0,new_complete_solves=0,source=journal.source_state,timings=journal.timings,
        continuum_accuracy=False,target_qualified=False,NN20=False)
    write_json(folder/'verification_scientific_result.json',result);return result
