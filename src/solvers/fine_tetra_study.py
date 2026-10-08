"""V63 narrow scope adapter; full solves use the existing tetra study."""
import gc
import json
import numpy as np
from src.runners.task042_shared import write_json
from . import fine_tetra_scope as scope
from .scattering_anchor import Journal,relative,save_arrays
from . import independent_tetra_reference as core


def preflight(folder,journal):
    from . import independent_tetra_scope as prior
    from .independent_tetra_study import load_boundary,checked
    from .scattering_accuracy_boundary import carrier_pair
    record=prior.stage('T5');spec=dict(record['spec'],triangle_backend='reachable_owner_support')
    s=core.make_setup(spec,record['physical'],journal)
    rows={}
    for q in (47,63):
        new=core.boundary(s,q,journal,folder);old=load_boundary(s,record['boundary_arrays'],record['mode_sha256'],q='q'+str(q))
        pair=carrier_pair(new['carrier'],old['carrier'],new['identities'],expected_modes=828)
        inc=relative(new['incident']-old['incident'],old['incident'])
        a=checked(new['arrays']);b=checked(old['arrays'])
        exact={key:bool(np.array_equal(a[key],b[key])) for key in ('offsets','rows','C','D','H','incident_traction')}
        rows[str(q)]=dict(pair=pair,incident=inc,exact=exact,support=new['support'],arrays=new['arrays'],parent=record['boundary_arrays']['q'+str(q)])
        if not pair['pass'] or inc>1e-11:raise ValueError('compressed T5 boundary/incident qualification')
        write_json(folder/f'support_q{q}.json',rows[str(q)]);del new,old;gc.collect()
    from .tetra_polynomial_difference import comparison
    old_pair=prior.stage('VERIFY_COST')['comparisons']['T4_T5']
    try:
        rebuilt=comparison(prior.stage('T4'),record,folder/'polynomial_qualification',journal)
        differences={k:dict(operation=abs(rebuilt['fields'][k]['difference_squared']-v['difference_squared'])/max(v['reference_squared'],1e-24),
            relative_norm=abs(np.sqrt(rebuilt['fields'][k]['difference_squared']/v['difference_squared'])-1)) for k,v in old_pair['fields'].items()}
        poly_pass=max(v['operation'] for v in differences.values())<=1e-10 and max(v['relative_norm'] for v in differences.values())<=1e-6 and rebuilt['pass_gate']==old_pair['pass_gate']
    except ValueError as exc:
        rebuilt=dict(error=str(exc));differences={};poly_pass=False
    write_json(folder/'polynomial_qualification.json',dict(pass_gate=poly_pass,differences=differences,parent=old_pair['arrays'],result=rebuilt))
    # Real refined TH3 geometry witness, using saved geometry only (no old PDE).
    from .tetra_polynomial_difference import parent_map
    coarse=core.CachedTetraEvaluator(s['V'],0,s['kappa'],quadrature_tables=False)
    fine=core.make_setup(prior.case_spec('TH3'),prior.physical_for('TH3'),journal)
    evaluator=core.CachedTetraEvaluator(fine['V'],0,fine['kappa'],quadrature_tables=False)
    parents=parent_map(coarse,evaluator)
    witness=save_arrays(folder/'real_TH3_containment.npz',parents=parents,geometry_x=fine['geometry']['geometry_x'],geometry_dofmap=fine['geometry']['geometry_dofmap'])
    return dict(status='COMPLETED',pass_gate=all(v['pair']['pass'] and v['incident']<=1e-11 for v in rows.values()),
        support=rows,polynomial_pass=poly_pass,polynomial_differences=differences,containment=witness,
        prior_solution_sha256=record['arrays']['sha256'],new_numeric_factors=0,new_complete_solves=0,
        source=journal.source_state,timings=journal.timings)


def execute(role,folder,state):
    budget=scope.memory_budget(role)
    if state.get('memory_budget')!=budget:raise ValueError('V63 live role memory propagation')
    journal=Journal(folder,window_scope=scope.window,planning_limit_bytes=budget['planning_gib']*2**30);journal.source_state=state
    if role=='PREFLIGHT':return preflight(folder,journal)
    if role in scope.SOLVES:
        from .independent_tetra_study import solve
        return solve(role,folder,journal,state,scope_module=scope)
    if role=='VERIFY_COST':
        from benchmarks.collect_fine_tetra import verify
        return verify(folder,journal)
    raise ValueError('V63 explicit stage')
