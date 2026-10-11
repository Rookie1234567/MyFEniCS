"""Unique V73 frozen consumer; all original audits and scoring remain independent."""
import json
from pathlib import Path
import numpy as np

from src.runners.task042_shared import write_json
from src.solvers import restart_feedback_scope as scope
from src.solvers.tetra_body_checkpoint import file_digest
from src.solvers.scattering_anchor_checks import checked_arrays
from src.solvers.scattering_anchor import relative
from benchmarks.collect_bounded_trace import numeric_saved_check


def verify(folder,journal):
    from src.solvers.bounded_trace_study import action_charge
    from benchmarks.collect_frozen_local_h import saved_original,first_normalization
    from benchmarks.check_independent_tetra import saved_pair
    from benchmarks.collect_exact_tetra import strict_reproduction
    from src.solvers.tetra_polynomial_difference import comparison
    from src.solvers.independent_tetra_fields import selected_points
    from src.solvers import assembly_tetra_scope as reference
    path=scope.verification_inventory_for('VERIFY_COST')
    if path is None or journal.source_state['verification_inventory']['sha256']!=file_digest(path):
        raise ValueError('V73 unique final freeze identity')
    freeze=json.loads(path.read_text());states=freeze['states'];rows={}
    # This is the first permission to consume the physical reference.
    parent=reference.stage('SOLVE') if states else None
    for role,frozen in states.items():
        r=scope.stage(role)
        if frozen['retained']['sha256']!=r['retained_returned']['sha256'] or frozen['array_sha256']!=r['arrays']['sha256']:
            raise ValueError('V73 route frozen array identity')
        root=Path(json.loads((scope.ARTIFACT/(role+'.json')).read_text())['path']).parent
        qualification=numeric_saved_check(Path(r.get('numeric_witness_root',root)),minimum_bytes=12*2**30)
        own=folder/role;own.mkdir(exist_ok=True)
        check=action_charge('V_'+role+'_public_original',lambda:saved_original(r,own,journal,body_q=15),scope=scope)
        pair=comparison(parent,r,own/'V70_pair',journal,coefficient_first=True)
        independent=saved_pair(pair,parent,r,expected_points=selected_points(r['physical']))
        if not independent['published_gate_matches_recalculation']:raise ValueError('V73 saved comparison decision')
        first=first_normalization(pair,parent,label='V70')
        # Reuse exact numerator, selected values and original reference norms.
        strict=strict_reproduction(pair)
        a=checked_arrays(pair['arrays']);denom_scores={}
        for name in pair['selected']:
            x=a['selected_'+name+'_first'];y=a['selected_'+name+'_second']
            denom_scores[name]=relative(y-x,x)
        fields={k:v['relative'] for k,v in first['fields'].items()}
        # first_normalization provides the fixed reference field and point scores.
        reference_pass=max(fields.values())<=1e-6 and max(denom_scores.values())<=1e-6
        reference_pass=bool(reference_pass and pair['modes']['outgoing_amplitude_at_boundary_relative']<=1e-6
            and max(pair['power_differences'].values())<=1e-8 and pair['modes']['mode_power_max_absolute']<=1e-9
            and max(pair['energies'])<=1e-5 and first['quadrature_operation_scaled']<=1e-10)
        reference_scores=dict(fields=fields,selected=denom_scores,pass_gate=reference_pass,
            same_numerator=pair['arrays'],reference_norms=first['reference_packets'])
        passed=check['pass_gate'] and scope.joint_equation_pass(r) and strict['pass_gate'] and reference_pass
        rows[role]=dict(qualification=qualification,independent_original=check,comparison=pair,
            independent_pair=independent,candidate_denominator=strict,reference_denominator=reference_scores,
            joint_equation_pass=scope.joint_equation_pass(r),strict_pass=bool(passed))
        write_json(own/'completed_independent_route.json',rows[role])
    result=dict(status='COMPLETED',consumer_pass=True,pass_gate=any(r['strict_pass'] for r in rows.values()),
        routes=rows,branch=freeze['branch'],frozen_inventory=dict(path=str(path),sha256=file_digest(path)),
        new_numeric_factors=0,new_complete_solves=0,source=journal.source_state,timings=journal.timings,
        continuum_accuracy=False,target_qualified=False,NN20=False)
    write_json(folder/'verification_scientific_result.json',result);return result
