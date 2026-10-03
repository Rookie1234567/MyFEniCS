"""Independent collector boundaries, legal negatives, optional audit receipts."""
from copy import deepcopy
import json
from types import SimpleNamespace
import numpy as np
import pytest
from benchmarks.collect_task042_return_direction import numeric as checked_numeric,inventory as checked_inventory,compact_inputs
from benchmarks.task042_admission_receipt import replay
from src.solvers.return_block_direction import extend_nine
from src.solvers.return_block_window import CAPS
from src.solvers.bounded_diagnostic_window import DiagnosticWindow
from src.runners import task042_shared as shared


def numeric(row,a,r,W9,cached_c9,cached_e9,ids):
    return checked_numeric(row,a,r,W9,cached_c9,cached_e9,ids,qj=W9[:,-1])


def inventory(result,plan):
    return checked_inventory(result,plan,sources=plan['fixture_sources'],ledger=result['fixture_ledger'],manifest=result['fixture_manifest'])


def fixture(kind='positive'):
    n=16;Q=np.eye(n,9,dtype=complex);r=np.ones(n,complex)*(1+.4j);r[8]=1.;d=np.zeros(n,complex)
    d[9:]=r[9:]
    if kind=='weak':d[9]=1;d[10:]=0
    if kind=='beta_zero':d[9]=1;d[10]=-1;d[11:]=0
    if kind=='zero':d[:]=0
    if kind=='duplicate':d[:]=0;d[0]=1
    if kind=='nearzero':d*=1e-200
    if kind=='solved':r[9:]=0
    row,a=extend_nine(r,Q,Q,r[:9],r-Q@r[:9],d,d,lambda x:x,bnorm=10.,old_scales=np.ones(9),new_scale=10.)
    row.update(name='V24-LZ-CYCLE4',old_operation_scales=[1.]*9)
    qj=Q[:,-1]*r[8];a.update(w=-d,aw=-d,feedback=np.zeros(n,complex),feedback_image=np.zeros(n,complex),return_direction=qj+d,return_image=qj+d)
    W=Q.copy();W[:,-1]=qj;old_c=r[:9].copy();old_c[-1]=1
    # The production last column is qJ, not a unit vector.
    row,a0=extend_nine(r,W,W,old_c,r-W@old_c,d,d,lambda x:x,bnorm=10.,old_scales=np.ones(9),new_scale=10.)
    a0.update({k:a[k] for k in ('w','aw','feedback','feedback_image','return_direction','return_image')})
    row.update(name='V24-LZ-CYCLE4',old_operation_scales=[1.]*9)
    ids=np.array([8]) if kind!='duplicate' else np.array([8])
    inside=np.isin(np.arange(n),ids)
    row['regions']={label:{key:float(np.linalg.norm(v[mask])) for key,v in [('qj_response_norm',W[:,-1]),('d_response_norm',d),('return_response_norm',qj+d),('old_e9_norm',a0['old_e9']),('new_e10_norm',a0['diagnostic_residual'])]} for label,mask in [('inside_J',inside),('outside_J',~inside)]}
    from src.test.task042_return_fixture import certify_flow
    certify_flow(row,a0,r,W,ids)
    return row,a0,r,W,old_c,r-W@old_c,ids


@pytest.mark.parametrize('kind',['positive','weak','beta_zero','zero','duplicate','nearzero','solved'])
def test_complete_and_legal_negative_certificates(kind):
    data=fixture(kind);out=numeric(*data)
    if kind=='positive':assert out['g10']<1e-12
    if kind in ('zero','duplicate','nearzero'):assert not out['new_direction_resolved'] and out['beta_zero_legal']
    if kind=='beta_zero':assert out['new_direction_resolved'] and abs(out['beta']['real'])<1e-12 and out['g10']==pytest.approx(1.)
    if kind=='solved':assert out['g10'] is None and out['classification']=='SOLVED_BASELINE'


@pytest.mark.parametrize('bad',['missing_gate','failed_gate','nan','inf','negative','false_g','wrong_certificate','bad_actual','bad_region'])
def test_no_status_label_can_override_raw_errors(bad):
    row,a,*rest=fixture()
    if bad=='missing_gate':row['gates'].pop('QR')
    if bad=='failed_gate':row['gates']['QR']=False
    if bad in ('nan','inf','negative'):row['eta10']={'nan':np.nan,'inf':np.inf,'negative':-1}[bad]
    if bad=='false_g':row['g10']=.5
    if bad=='wrong_certificate':a['projection_coefficients'][0]+=1
    if bad=='bad_actual':a['original_combination_image'][0]+=1
    if bad=='bad_region':row['regions']['inside_J']['new_e10_norm']+=1
    with pytest.raises(ValueError):numeric(row,a,*rest)


def inventory_fixture():
    from benchmarks.collect_task042_return_direction import NAMES,IDENTITIES
    plan={k:'a'*64 for k in IDENTITIES};plan['states']=[dict(name=n,parent_result=dict(path='/parent/'+n,sha256='b'*64),state={},v25_arrays={},v26_arrays={}) for n in NAMES]
    for x in plan['states']:
        for key in ('state','v25_arrays','v26_arrays'):x[key]={'sha256':'c'*64,'path':'/'+key+x['name']}
    counts=dict.fromkeys(CAPS,0);counts.update(actions=36,factor_readers=7,outer_lu_solve=24,joint_lu_solve=4,explicit_triangular_pass=56,thin_decompositions=2,port_factors=1,port_solves=35,port_rhs_columns=35)
    result=dict(rows=[dict(name=x['name'],parent_result=x['parent_result'],input_state=x['state'],v25_arrays=x['v25_arrays'],v26_arrays=x['v26_arrays']) for x in plan['states']],budget_counts=counts,action_counts=dict(S=34,SH=2,audit=0),status='DIAGNOSTIC_COMPLETE',reference_arrays_read=False,Q_U_R_D_L_loaded=False,new_solver_states=0,global_p4_factor_constructed=False,operator_identity={k:plan[k] for k in IDENTITIES},operator_packet={'sha256':plan['action_sha256']},complete_ports=40,source_sha='d'*40)
    from src.test.task042_return_fixture import certify_inventory
    certify_inventory(result,plan)
    return result,plan


def test_parent_mapping_and_budget_inventory():
    r,p=inventory_fixture();assert len(inventory(r,p))==2
    assert all(x['parent_result'] for x in compact_inputs(p))


@pytest.mark.parametrize('bad',['empty','duplicate','label','null','member','budget','nan_budget','missing_budget','bool_budget','action','failed','mode'])
def test_inventory_rejects(bad):
    r,p=inventory_fixture()
    if bad=='empty':r['rows']=[]
    if bad=='duplicate':r['rows'][1]=r['rows'][0]
    if bad=='label':r['rows'][0]['name']='INITIAL'
    if bad=='null':r['rows'][0]['parent_result']=None
    if bad=='member':r['rows'][0]['input_state']={'path':'other'}
    if bad=='budget':r['budget_counts']['actions']=65
    if bad=='nan_budget':r['budget_counts']['actions']=np.nan
    if bad=='missing_budget':r['budget_counts'].pop('port_solves')
    if bad=='bool_budget':r['budget_counts']['actions']=True
    if bad=='action':r['action_counts']['SH']=3
    if bad=='failed':r['status']='FAILED'
    if bad=='mode':r['operator_identity']['mode_sha256']='e'*64
    with pytest.raises(ValueError):inventory(r,p)


@pytest.mark.parametrize('rejected',[True,False])
def test_optional_audit_receipt_replay_and_unchanged_default(tmp_path,monkeypatch,rejected):
    topo=[dict(cpu=0,core=0,socket=0,siblings=[0,1]),dict(cpu=1,core=0,socket=0,siblings=[0,1])]
    first={0:[0,0,0,100,0,0,0,0],1:[0,0,0,100,0,0,0,0]}
    last={0:[10 if rejected else 0,0,0,190 if rejected else 200,0,0,0,0],1:[0,0,0,200,0,0,0,0]}
    fractions={cpu:1-(last[cpu][3]-first[cpu][3])/100 for cpu in first};neighbors=[];deltas={}
    candidates=shared.spare_cores(topo,neighbors,fractions,deltas)
    assert candidates==([] if rejected else [0,1])
    def fake(*,observed_activity,observation=None):
        if observation is not None:
            observation.update(allowed_cpus=[0,1],sample_interval_seconds=1.,topology=topo,neighbor_processes=[],cpu_ticks_before=first,cpu_ticks_after=last,cpu_busy_fractions=fractions,thread_ticks_before={},thread_ticks_after={},thread_delta_ticks={},candidate_cpus=candidates,cpu_decisions=shared.cpu_exclusions(topo,[],fractions,{}))
            observation['gates']['CPU_SMT']='FAIL' if rejected else 'PASS'
        if rejected:raise RuntimeError('No audited unoccupied physical core')
        return {'cpu':0,'candidate_cpus':[0,1]}
    monkeypatch.setattr(shared,'_audit',fake);path=tmp_path/'receipt.json'
    if rejected:
        with pytest.raises(RuntimeError):shared.audit(observed_activity=True,receipt_path=path,input_path='/actual.dat')
    else:assert shared.audit(observed_activity=True,receipt_path=path,input_path='/actual.dat')==shared.audit(observed_activity=True)
    value=json.loads(path.read_text());assert replay(value)['CPU_SMT']==('FAIL' if rejected else 'PASS')
    assert value['input_path']=='/actual.dat' and value['gates']['MEMORY']=='NOT_CHECKED'


def test_carried_cost_and_real_closed_window_not_used(tmp_path,monkeypatch):
    w=DiagnosticWindow(tmp_path,{'actions':64},'V28',carried_auxiliary_seconds=12.366657367907465)
    (tmp_path/'aux_fixture').mkdir();(tmp_path/'aux_fixture/summary.json').write_text('{"elapsed_seconds":3}')
    assert w.auxiliary_wall()==pytest.approx(15.366657367907465)


def test_v28_real_schema_registered_without_v27_reroute(monkeypatch,tmp_path):
    from src.io import return_block_diagnostic as old,return_block_continuation as new
    from src.io.task042_profile import TASK042_PROFILES
    plan=json.loads(new.PLAN_PATH.read_text());local=tmp_path/'plan.json';local.write_text(json.dumps(plan));monkeypatch.setattr(new,'PLAN_PATH',local)
    w=DiagnosticWindow(tmp_path,CAPS,'V28',carried_auxiliary_seconds=12.366657367907465)
    monkeypatch.setattr(w,'require_live',lambda **k:dict(heavy_remaining_seconds=4000))
    new_window=SimpleNamespace(TMP=tmp_path,ledger=w.ledger,auxiliary_wall=w.auxiliary_wall,require_live=w.require_live)
    monkeypatch.setattr(new,'window',new_window)
    spec=new.load_return_diagnostic('input/task042_neural_coarse_inverse/v28_return_direction_diagnostic.dat')
    assert spec.derived['stage']==TASK042_PROFILES['task042_v28_diagnostic']=='V28-DIAGNOSTIC'
    assert old.load_return_diagnostic('input/task042_neural_coarse_inverse/v28_return_direction_diagnostic.dat') is None
    assert new.load_return_diagnostic('input/task042_neural_coarse_inverse/v27_return_direction_diagnostic.dat') is None
    (tmp_path/'formal_admission_attempt.json').write_text('{}')
    from src.io.input_loader import InputError
    with pytest.raises(InputError):new.load_return_diagnostic('input/task042_neural_coarse_inverse/v28_return_direction_diagnostic.dat')
