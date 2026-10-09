"""V67 frozen saved consumers reuse the existing independent mathematical loops."""
import json
from src.runners.task042_shared import write_json
from src.solvers import local_p_mode_scope as scope
from benchmarks.collect_frozen_local_h import saved_original,first_normalization,project_old_field
from benchmarks.collect_independent_tetra import digest


def verify(folder,journal):
    from src.solvers.tetra_polynomial_difference import comparison
    from src.solvers.independent_tetra_fields import selected_points
    from benchmarks.check_independent_tetra import saved_pair
    from src.solvers import frozen_local_h_scope as L4,p6_completion_scope as P6
    path=scope.verification_inventory_for('VERIFY_COST')
    if path is None or journal.source_state.get('verification_inventory',{}).get('sha256')!=digest(path):raise ValueError('V67 frozen inventory')
    frozen=json.loads(path.read_text());checks={};pairs={};independent={};normalizations={}
    for name,role in (('L5','SOLVE_COMPLETE'),('M4','M4')):
        if name not in frozen['states']:continue
        r=scope.stage(role)
        if r['arrays']['sha256']!=frozen['states'][name]['array_sha256']:raise ValueError('V67 frozen coefficients')
        own=folder/name;own.mkdir(exist_ok=True)
        checks[name]=saved_original(r,own,journal,body_q=2*r['spec']['degree']+5)
        parents=[('L4F',L4.stage('SOLVE_COMPLETE'))]
        if name=='L5':parents.append(('P6',P6.stage('SOLVE_COMPLETE')))
        else:
            sub=own/'projected_L4F';sub.mkdir(exist_ok=True)
            parents=[('L4F',project_old_field(parents[0][1],r,sub,journal))]
        for label,parent in parents:
            key=label+'_'+name;pair=comparison(parent,r,folder/key,journal)
            check=saved_pair(pair,parent,r,expected_points=selected_points(r['physical']))
            if not check['published_gate_matches_recalculation']:raise ValueError('V67 independent saved score')
            alt=first_normalization(pair,parent,label=label)
            write_json(folder/(key+'_first_denominator.json'),alt)
            pairs[key]=pair;independent[key]=check;normalizations[key]=alt
            write_json(folder/'saved_pair_progress.json',dict(comparisons=pairs,independent=independent,first_normalizations=normalizations))
    result=dict(status='COMPLETED',checks=checks,comparisons=pairs,independent_pairs=independent,first_normalizations=normalizations,
        returned_states=list(frozen['states']),new_numeric_factors=0,new_complete_solves=0,source=journal.source_state,timings=journal.timings,
        continuum_accuracy=False,target_qualified=False,NN20=False)
    write_json(folder/'verification_scientific_result.json',result);return result
