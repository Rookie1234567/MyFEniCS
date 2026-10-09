"""Independent saved V66 consumers; no matrix assembly, factor or solve."""
import gc
import json
from pathlib import Path
import numpy as np
from src.runners.task042_shared import write_json
from src.solvers import frozen_local_h_scope as scope
from src.solvers.scattering_anchor import save_arrays,relative
from src.solvers.scattering_anchor_checks import checked_arrays
from src.postprocessing.paired_field_norms import score_differences,NAMES
from benchmarks.collect_independent_tetra import restored,saved_output_check,digest


def saved_original(record,folder,journal,*,body_q=13):
    from src.solvers.independent_tetra_study import load_boundary
    from src.solvers.independent_tetra_fields import tangential_check
    from src.solvers.tetra_coefficient_action import CoefficientFullAction
    s,v,f=restored(record,journal);b=load_boundary(s,record['boundary_arrays'],record['mode_sha256'],'q63')
    action=CoefficientFullAction(s,b,body_q);audit,res,rhs=action.audit(v['x'],v['rhs'],journal)
    arrays=save_arrays(folder/'independent_original.npz',x=v['x'],residual=res,rhs=rhs,action=rhs-res)
    old=checked_arrays(record['audit']['arrays']);op=relative(res-old['residual'],rhs)
    tangent=tangential_check(s,f,folder);output=saved_output_check(record)
    result=dict(original=audit,arrays=arrays,producer_consumer_operation=op,tangential=tangent,output=output,
        pass_gate=audit['pass_gate'] and op<=1e-10 and tangent['pass_gate'] and output['pass_gate'])
    write_json(folder/'saved_checker.json',result)
    del s,v,f,b,action;gc.collect();return result


def first_normalization(pair,first,*,label='P6'):
    """Pure arrays: common L4 subcell numerator, saved P6 global norm."""
    cached=checked_arrays(pair['arrays']);numerator=cached['per_cell_integrals'][:,:,0].sum(axis=0)
    norms=[]
    for row in first['output']['integrals']:
        a=checked_arrays(row['arrays'])
        norms.append(dict(q=row['q'],reference=np.r_[a['per_cell_total_squared'].sum(axis=0),a['per_cell_analytic_squared'][:,:,0].sum(axis=0)],arrays=row['arrays']))
    if [r['q'] for r in norms]!=[23,31]:raise ValueError('P6 saved denominator q23/q31 inventory')
    result=score_differences(numerator,norms[-1]['reference'],
        {n:cached['selected_'+n+'_first'] for n in NAMES},{n:cached['selected_'+n+'_second'] for n in NAMES})
    op=float(np.max(np.abs(norms[0]['reference']-norms[1]['reference'])/np.maximum(norms[-1]['reference'],1e-24)))
    physical=pair['modes']['outgoing_amplitude_at_boundary_relative']<=1e-4 and pair['modes']['mode_power_max_absolute']<=1e-6 and max(pair['power_differences'].values())<=1e-5 and max(pair['energies'])<=1e-5
    result.update(denominator=label,parent_sha256=first['arrays']['sha256'],common_numerator=pair['arrays'],reference_packets=norms,
        quadrature_operation_scaled=op,pass_gate=result['field_and_selected_pass'] and physical and op<=1e-10)
    return result


def project_old_field(first,new,folder,journal):
    """Actual all-mode surface projection without changing the old field."""
    from src.solvers.independent_tetra_reference import make_setup
    from src.solvers.independent_tetra_study import load_boundary
    from src.solvers.dtn_port_3d import _port_power_metrics,_write_port_outputs
    v=checked_arrays(first['arrays']);s=make_setup(new['spec'],new['physical'],journal)
    for key in s['geometry']:
        if not np.array_equal(s['geometry'][key],v[key]):raise ValueError('conditional M unchanged actual mesh')
    if not np.array_equal(s['masters'],v['masters']) or not np.array_equal(s['kappa'],v['kappa']):raise ValueError('conditional M unchanged field coordinates')
    boundary=load_boundary(s,new['boundary_arrays'],new['mode_sha256'],'q63')
    with journal.measured('unchanged_L4F_actual_all1188_mode_projection'):
        entries=boundary['carrier'].entries
        port=np.array([np.dot(e.projection_values,v['u_native'][e.projection_rows])/e.normalization_h for e in entries])
        if port.shape!=(1188,) or not np.all(np.isfinite(port)):raise ValueError('complete finite new mode projection')
        pm=_port_power_metrics(s['cfg'],list(boundary['modes']),port,list(boundary['projections']))
        _write_port_outputs(folder,s['cfg'],list(boundary['modes']),port,list(boundary['projections']),pm,s['mesh'].comm)
    journal.calls['port_recovery']=journal.calls.get('port_recovery',0)+1
    receipt=save_arrays(folder/'old_L4F_on_all1188.npz',port=port)
    projected=dict(first,mode_power_path=str(folder/'port_power.json'),output=dict(first['output'],port_metrics=pm))
    projected['finite_mode_projection']=dict(arrays=receipt,parent=first['arrays'],mode_sha256=new['mode_sha256'],
        new_modes_actual=360,old_port_not_overwritten=True)
    write_json(folder/'new_mode_projection.json',projected['finite_mode_projection'])
    return projected


def verify(role,folder,journal):
    from src.solvers.tetra_polynomial_difference import comparison
    from benchmarks.check_independent_tetra import saved_pair
    from src.solvers.independent_tetra_fields import selected_points
    path=scope.verification_inventory_for(role)
    if path is None or journal.source_state.get('verification_inventory',{}).get('sha256')!=digest(path):raise ValueError('V66 live frozen consumer inventory')
    frozen=json.loads(path.read_text());checks={};pairs={}
    if role=='COMPARE_GATE':
        r=scope.stage('SOLVE_COMPLETE')
        if frozen['states']['L4F']['array_sha256']!=r['arrays']['sha256']:raise ValueError('V66 frozen L4F coefficients')
        checks['L4F']=saved_original(r,folder,journal)
        from src.solvers import p6_completion_scope as P6, fine_tetra_scope as AB
        p=P6.stage('SOLVE_COMPLETE');pair=comparison(p,r,folder/'P6_L4F',journal)
        independent=saved_pair(pair,p,r,expected_points=selected_points(r['physical']))
        if not independent['published_gate_matches_recalculation']:raise ValueError('P6/L4F independent saved score')
        alternative=first_normalization(pair,p);write_json(folder/'P6_denominator.json',alternative)
        pairs['P6_L4F']=pair
        # Same common child domain; only the mandated A auxiliary comparison.
        a=AB.stage('A');pairs['A_L4F']=comparison(a,r,folder/'A_L4F',journal)
        joint=pair['pass_gate'] and alternative['pass_gate']
        physical=checks['L4F']['pass_gate'] and p['equation_pass'] and r['equation_pass']
        result=dict(status='COMPLETED',checks=checks,comparisons=pairs,independent_pair=independent,
            P6_normalization=alternative,joint_space_pass=joint,complete_physical_pass=physical,
            branch=dict(L4M_numerically_admitted=joint and physical,reason='joint dual-normalization spatial/physical checks' if joint and physical else 'joint spatial/physical gate failed'))
    else:
        # Every prior original audit is reused by receipt; no repeated PDE.
        if (scope.ARTIFACT/'COMPARE_GATE.json').exists():
            gate=scope.stage('COMPARE_GATE');checks['L4F']=gate['checks']['L4F'];pairs=gate['comparisons']
        if 'L4M' in frozen.get('states',{}):
            m=scope.stage('L4M')
            if frozen['states']['L4M']['array_sha256']!=m['arrays']['sha256']:raise ValueError('V66 frozen M coefficients')
            checks['L4M']=saved_original(m,folder,journal)
            f=scope.stage('SOLVE_COMPLETE');sub=folder/'projected_L4F';sub.mkdir(exist_ok=True)
            projected=project_old_field(f,m,sub,journal)
            pairs['L4F_L4M']=comparison(projected,m,folder/'L4F_L4M',journal)
        result=dict(status='COMPLETED',checks=checks,comparisons=pairs,returned_states=list(frozen.get('states',{})),
            branch=scope.stage('COMPARE_GATE')['branch'] if (scope.ARTIFACT/'COMPARE_GATE.json').exists() else dict(reason='no returned L4F'),
            prior_audit_not_replayed=True)
    result.update(new_numeric_factors=0,new_complete_solves=0,source=journal.source_state,timings=journal.timings,
        continuum_accuracy=False,target_qualified=False,NN20=False)
    write_json(folder/'verification_scientific_result.json',result);return result
