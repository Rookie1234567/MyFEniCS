"""End-to-end synthetic collector acceptance and review's four counterexamples."""
from copy import deepcopy
import json
import numpy as np
import pytest
from benchmarks.collect_task042_return_direction import collect,numeric,inventory
from src.test.task042_return_fixture import complete_packet,republish,arrays_receipt,json_receipt
from src.test.test_task042_v28_cached_checker import fixture,inventory_fixture


@pytest.mark.parametrize('kind',['positive','weak','beta_zero','zero','duplicate','nearzero','solved'])
def test_complete_collector_and_legal_negatives(tmp_path,kind):
    args,raw,result=complete_packet(tmp_path,kind)
    out=collect(**args)
    assert out['status']=='CHECKED' and len(out['rows'])==2
    assert result['rows'][0]['parent_result']!=result['rows'][1]['parent_result']
    assert result['rows'][0]['input_state']['z_sha256']!=result['rows'][1]['input_state']['z_sha256']
    if kind=='positive':assert out['decision']=='RETURN_EXTRA_DIRECTION_SIGNAL'
    if kind in ('zero','duplicate','nearzero'):assert out['decision']=='REDUNDANT_OR_UNRESOLVED'
    if kind=='beta_zero':assert all(x['beta_zero_legal'] for x in out['rows'])
    if kind=='solved':assert all(x['g10'] is None for x in out['rows'])


@pytest.mark.parametrize('bad',['zero_consumption','missing_factor','duplicate_factor','failed_factor','wrong_factor_source',
    'wrong_factor_rows','wrong_factor_hash','wrong_seed','bad_solve','missing_witness','nan_witness','port_shape','port_columns',
    'ledger_counts','ledger_source','manifest_counts','wrong_parent','wrong_member','missing_arrays','return_vector',
    'residual_norm','w_support','feedback_support','missing_identity','failed_identity','cancellation','missing_scale',
    'wrong_recombination','state_concat','state_port','missing_state_audit','nonfinite'])
def test_full_chain_rejects_incomplete_or_inconsistent_evidence(tmp_path,bad):
    args,raw,result=complete_packet(tmp_path);row=result['rows'][0]
    if bad=='zero_consumption':
        result['budget_counts'].update(actions=0,port_solves=0,port_rhs_columns=0);result['action_counts'].update(S=0,SH=0)
    elif bad=='missing_factor':result['factor_reloads'].pop()
    elif bad=='duplicate_factor':result['factor_reloads'][-1]=deepcopy(result['factor_reloads'][0])
    elif bad=='failed_factor':result['factor_reloads'][0]['qualified']=False
    elif bad=='wrong_factor_source':result['factor_reloads'][0]['source_sha']='0'*40
    elif bad=='wrong_factor_rows':result['factor_reloads'][0]['rows_sha256']='0'*64
    elif bad=='wrong_factor_hash':result['factor_reloads'][0]['files'][0]['array_sha256']='0'*64
    elif bad=='wrong_seed':result['factor_reloads'][0]['witnesses'][0]['seed']+=1
    elif bad=='bad_solve':result['factor_reloads'][0]['witnesses'][0]['solve_error_norm']=1.
    elif bad=='missing_witness':result['factor_reloads'][0]['witnesses']=[]
    elif bad=='nan_witness':result['factor_reloads'][0]['witnesses'][0]['solve_relative']=float('nan')
    elif bad=='port_shape':result['port_rhs_inventory'][0]['shape']=[40,1]
    elif bad=='port_columns':result['port_rhs_inventory'][0]['RHS_columns']=2
    elif bad.startswith('ledger'):
        p=args['ledger_path'];ledger=json.loads(p.read_text())
        if bad=='ledger_counts':ledger['runs'][0]['counts']['actions']=0
        else:ledger['runs'][0]['source_sha']='0'*40
        json_receipt(p,ledger)
    elif bad=='manifest_counts':
        p=result['run_manifest']['path'];manifest=json.loads(open(p).read());manifest['completed_budget_counts']['actions']=0
        result['run_manifest']=json_receipt(__import__('pathlib').Path(p),manifest)
    elif bad=='wrong_parent':row['parent_result']=deepcopy(result['rows'][1]['parent_result'])
    elif bad=='wrong_member':row['input_state']['z_sha256']='0'*64
    elif bad=='missing_arrays':row['diagnostic_arrays']={}
    elif bad=='residual_norm':row['residual_norm']*=2
    elif bad=='missing_identity':row.pop('identity')
    elif bad=='failed_identity':row['identity']['port_reclosure_operation_relative']=1.
    elif bad=='cancellation':row['cancellation']['error_norm']=1.
    elif bad=='missing_scale':row.pop('scale_provenance')
    elif bad=='wrong_recombination':row['independent_recombination']['operation_relative']=1.
    elif bad in ('return_vector','w_support','feedback_support','missing_state_audit','nonfinite'):
        p=__import__('pathlib').Path(row['diagnostic_arrays']['path'])
        with np.load(p,allow_pickle=False) as f:a={k:np.array(f[k]) for k in f.files}
        if bad=='return_vector':a['return_direction'][0]+=100
        elif bad=='w_support':a['w'][8]+=1
        elif bad=='feedback_support':a['feedback'][0]+=1
        elif bad=='missing_state_audit':a.pop('audited_full_residual')
        else:a['return_direction'][0]=float('inf')
        row['diagnostic_arrays']=arrays_receipt(p,**a)
    elif bad in ('state_concat','state_port'):
        # Rebind all container receipts, so the independent array certificate
        # (rather than just an obsolete hash) must reject the wrong state.
        p=__import__('pathlib').Path(row['input_state']['path'])
        with np.load(p,allow_pickle=False) as f:a={k:np.array(f[k]) for k in f.files}
        if bad=='state_concat':a['z'][0]+=1
        else:a['port'][0]+=1;a['z'][16:]=a['port']
        ref=arrays_receipt(p,**a);old=row['input_state'];row['input_state']=ref
        plan=json.loads(args['plan_path'].read_text());plan['states'][0]['state']=ref
        parent_path=__import__('pathlib').Path(row['parent_result']['path']);parent=json.loads(parent_path.read_text())
        parent['cycles'][3]['state']=ref;parent['start']['state']=ref
        parent_ref=json_receipt(parent_path,parent);row['parent_result']=parent_ref
        plan['states'][0]['parent_result']=parent_ref
        prior=json.loads(open(plan['v26_result']['path']).read());prior['rows'][0]['input_state']=ref
        plan['v26_result']=json_receipt(__import__('pathlib').Path(plan['v26_result']['path']),prior)
        old_result=json.loads(open(plan['v25_result']['path']).read())
        for rr in old_result['rows']:
            if rr['input_state']==old:rr['input_state']=ref
        plan['v25_result']=json_receipt(__import__('pathlib').Path(plan['v25_result']['path']),old_result)
        for item in args['old_plan']['states']:
            if item['state']==old:item.update(state=ref,parent_result=parent_ref)
        json_receipt(args['plan_path'],plan);result['plan_sha256']=__import__('src.solvers.neural_fe_action_packet',fromlist=['file_hash']).file_hash(args['plan_path'])
        mp=__import__('pathlib').Path(result['run_manifest']['path']);manifest=json.loads(mp.read_text());manifest['plan_sha256']=result['plan_sha256']
        result['run_manifest']=json_receipt(mp,manifest)
    # Raw JSON needs allow_nan for a deliberately broken certificate. Production
    # writer correctly disallows it; the reader must still reject imported data.
    raw.write_text(json.dumps(result,allow_nan=True))
    json_receipt(raw.parent/'DIAGNOSTIC.json',dict(path=str(raw),sha256=__import__('src.solvers.neural_fe_action_packet',fromlist=['file_hash']).file_hash(raw)))
    with pytest.raises((ValueError,KeyError,OSError)):
        collect(**args)


def test_partial_result_never_classified_checked(tmp_path):
    args,raw,result=complete_packet(tmp_path);result['status']='JOINT_RELOAD_UNSAFE';republish(raw,result)
    out=collect(**args);assert out['status']=='PARTIAL_UNRESOLVED'
    assert all(x['g10'] is None for x in out['rows'])


def test_four_review_counterexamples_rejected():
    r,p=inventory_fixture();r['budget_counts'].update(actions=0,port_solves=0,port_rhs_columns=0);r['action_counts'].update(S=0,SH=0)
    with pytest.raises(ValueError):inventory(r,p,sources=p['fixture_sources'],ledger=r['fixture_ledger'],manifest=r['fixture_manifest'])
    r,p=inventory_fixture();r['factor_reloads']=[dict(block='J',qualified=False,witnesses=[])]
    with pytest.raises(ValueError):inventory(r,p,sources=p['fixture_sources'],ledger=r['fixture_ledger'],manifest=r['fixture_manifest'])
    for broken in ('return','norm'):
        row,a,r,W,c,e,ids=fixture()
        if broken=='return':a['return_direction'][0]+=100
        else:row['residual_norm']*=2
        with pytest.raises(ValueError):numeric(row,a,r,W,c,e,ids,qj=W[:,-1])
