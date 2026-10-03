"""Fixed full-input study, saved-array checker and isolated quota regressions."""
from copy import deepcopy
import json
import shutil
from types import SimpleNamespace
import numpy as np
import pytest
from src.test.task042_v31_workflow_fixture import workflow
from src.solvers.full_input_block_correction import (CAPS, EXPECTED, direct_input,
    support_inventory, decision, FAMILY)


def test_actual_study_saved_arrays_accounting_and_independent_checker(tmp_path,monkeypatch):
    result,checked,book=workflow(tmp_path,monkeypatch,batch='v33')
    assert checked['status']=='CHECKED' and len(checked['rows'])==2
    assert result['budget_counts']==EXPECTED==book['charged']
    assert result['action_counts']==dict(S=20,SH=2,audit=0)
    assert result['selected_old_outer_LU_blocks']==[] and len(result['factor_reloads'])==1
    assert result['factor_reloads'][0]['solve_calls']==4
    assert not list((tmp_path/'records').glob('*v32*'))
    assert all(x['checks']['J_delta_cancellation']['full_b_relative']<=1e-11 for x in result['rows'])
    from benchmarks.task042_full_input_checker import numeric,consumption
    from benchmarks.collect_task042_return_direction import load_members
    from benchmarks.task042_return_certificates import factor_sources
    plan=json.loads((tmp_path/'plan.json').read_text());row=result['rows'][0];item=plan['states'][0]
    art=tmp_path/'benchmarks/artifacts/task042';n=18144
    setup=json.loads(__import__('pathlib').Path(plan['local_setup']['path']).read_text())
    groups=np.empty(n,np.int64)
    for b,p in enumerate(setup['block_inventory']):groups[p['rows']]=b
    ids=np.flatnonzero((groups==5)|(groups==7))
    state=load_members(item['state'],('trace','port','z','residual'),art/'v24')
    d=load_members(item['v25_arrays'],('directions','images'),art/'v25')
    j=load_members(item['v26_arrays'],('joint_direction','joint_image'),art/'v26')
    ret=load_members(item['v32_arrays'],('return_direction','return_image'),art/'v32')
    from src.solvers.full_input_block_correction import VECTOR_KEYS
    a=load_members(row['diagnostic_arrays'],VECTOR_KEYS,art/'v33')
    # Each mutation checks a named semantic failure, never an arbitrary OSError.
    for member in ('qfull','delta','aqfull','aqret_cached'):
        bad={k:v.copy() for k,v in a.items()};bad[member][0]+=.1
        with pytest.raises(ValueError,match='identity|bound|scale|unsafe|cached'):
            numeric(row,bad,state,d,j,ret,groups,ids,n)
    for value in (0.,2.):
        bad=deepcopy(row);bad['rho_full']=value
        with pytest.raises(ValueError,match='rho_full'):
            numeric(bad,a,state,d,j,ret,groups,ids,n)
    dd={k:v.copy() for k,v in d.items()};dd['directions'][:,[0,1]]=dd['directions'][:,[1,0]]
    with pytest.raises(ValueError,match='support'):numeric(row,a,state,dd,j,ret,groups,ids,n)
    bad=deepcopy(row);bad['trustworthy']=False
    with pytest.raises(ValueError,match='untrusted'):numeric(bad,a,state,d,j,ret,groups,ids,n)
    manifest=json.loads(__import__('pathlib').Path(result['run_manifest']['path']).read_text())
    prior=json.loads(__import__('pathlib').Path(plan['v26_result']['path']).read_text())
    sources=factor_sources(setup,prior,plan)
    for change in ('actions','joint_lu_solve','factor_readers','port_rhs_columns'):
        bad=deepcopy(result);bad['budget_counts'][change]-=1
        with pytest.raises(ValueError,match='consumption'):consumption(bad,plan,sources,book,manifest)
    bad=deepcopy(result);bad['factor_reloads'][0]['qualified']=False
    with pytest.raises(ValueError,match='factor'):consumption(bad,plan,sources,book,manifest)
    shutil.rmtree(tmp_path)


def test_fixed_small_matrices_difference_external_only_zero_and_singular():
    from benchmarks.task042_full_block_algebra import fixtures,embedded_inverse
    for name,A,J,O in fixtures():
        n=len(A);I=np.eye(n,dtype=complex)
        if name=='SINGULAR_LOCAL_2':
            with pytest.raises(np.linalg.LinAlgError):embedded_inverse(A,[J])
            continue
        BJ=embedded_inverse(A,[J]);LO=embedded_inverse(A,O)
        Bret=BJ-(I-BJ@A)@LO@A@BJ
        Bfull=BJ+(I-BJ@A)@LO@(I-A@BJ)
        for r in (np.arange(1,n+1)*(1+.2j),np.zeros(n,complex),
                  np.asarray([0 if i in J else 1j for i in range(n)])):
            d=np.zeros((n,8),complex);w=np.zeros_like(d)
            for b,rows in zip((0,1,2,3,4,6),O):
                d[rows,b]=np.linalg.solve(A[np.ix_(rows,rows)],r[rows]);w[:,b]=A@d[:,b]
            ids=np.array(J);actions=[];solves=[]
            def apply(x):actions.append(1);return A@x
            def solve(x):solves.append(1);return np.linalg.solve(A[np.ix_(J,J)],x)
            a,_=direct_input(d,w,BJ@r,Bret@r,ids,solve,apply,lambda x:np.linalg.norm(A)*np.linalg.norm(x))
            assert len(actions)==6 and len(solves)==1
            np.testing.assert_allclose(a['qfull'],Bfull@r,rtol=1e-12,atol=1e-12)
            np.testing.assert_allclose(a['adelta'][J],0,atol=1e-12)
            if not np.any(r):assert all(not np.any(v) for v in a.values())
            if name=='NON_CONTRACTION_2' and r[0]==0 and np.any(r):
                assert np.linalg.norm(r-a['aqfull'])/np.linalg.norm(r)==6.


def test_qualified_negative_and_zero_control_do_not_fabricate_neural_gain():
    names=('V24-LZ-CYCLE4','V24-LCZ-CYCLE4')
    rows=[dict(name=n,trustworthy=True,rho_full=6.,rho0=1.) for n in names]
    assert decision(rows)=='FULL_INPUT_FIXED_STEP_INSUFFICIENT'
    assert decision([dict(x,rho_full=.1,rho0=0.) for x in rows])=='FULL_INPUT_FIXED_STEP_INSUFFICIENT'
    assert decision([dict(x,rho_full=.1,rho0=1.) for x in rows])=='FULL_INPUT_SINGLE_STEP_SIGNAL'
    assert decision([dict(rows[0],trustworthy=False),rows[1]])=='NUMERICALLY_UNRESOLVED'


def test_storage_v33_extends_scope_without_changing_v32(tmp_path):
    from src.runners.diagnostic_storage import inventory
    for rel in ('tmp/task042/v33/a','tmp/task042/review_v30/a',
        'docs/task042_neural_coarse_inverse/outcomes/records/review_v30_test.json',
        'results/task042/task042_v33_diag/a'):
        p=tmp_path/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'12345')
    assert inventory(tmp_path,batch=33)['cumulative']['bytes']==20
    assert inventory(tmp_path,batch=33)['new']['bytes']==10
    old=inventory(tmp_path,batch=32,include_files=True)
    assert old['cumulative']['bytes']==5
    assert set(old['cumulative']['files'])=={'docs/task042_neural_coarse_inverse/outcomes/records/review_v30_test.json'}


def test_namespace_closed_and_zero_consumption_repair_boundary(tmp_path,monkeypatch):
    from src.io import full_input_block_v33 as io,return_block_v32 as old
    from src.solvers import full_input_block_v33_window as w
    from src.io.input_loader import InputError
    from src.io.task042_profile import TASK042_PROFILES
    dat='input/task042_neural_coarse_inverse/v33_full_input_diagnostic.dat'
    assert old.load_return_diagnostic(dat) is None
    book=dict(closed=False,active=None,runs=[],actor_wall_seconds=0.)
    fake=SimpleNamespace(TMP=tmp_path,require_qualification=lambda: {},
        require_live=lambda **kw:dict(heavy_remaining_seconds=4000),ledger=lambda:book,
        auxiliary_wall=lambda:151.4889468078036,actor_timeout=lambda *a:180.,allow_entry_repair=lambda:False)
    monkeypatch.setattr(io,'window',fake)
    spec=io.load_return_diagnostic(dat)
    assert spec.derived['stage']==TASK042_PROFILES['task042_v33_diagnostic']=='V33-DIAGNOSTIC'
    assert spec.derived['decoder_family']==FAMILY and spec.execution['timeout_seconds']==180.
    for closed,active,runs in ((True,None,[]),(False,{},[]),(False,None,[{}])):
        book.update(closed=closed,active=active,runs=runs)
        with pytest.raises(InputError,match='closed/active'):io.load_return_diagnostic(dat)
    monkeypatch.setattr(w,'ledger',lambda:book)
    book.update(closed=False,active=None,runs=[dict(classification='WORKER_FAILED',counts=dict.fromkeys(CAPS,0),upper=dict.fromkeys(CAPS,0),descendants_cleared=True)])
    assert w.allow_entry_repair()
    book['runs'][0]['upper']['port_factors']=1;assert not w.allow_entry_repair()
    book['runs'][0]['upper']['port_factors']=0;book['runs'][0]['classification']='RESOURCE_STOP';assert not w.allow_entry_repair()


def test_column_support_inventory_rejects_swap():
    groups=np.arange(8);d=np.eye(8,dtype=complex);w=d.copy()
    support_inventory(d,w,groups,8)
    with pytest.raises(ValueError,match='support'):support_inventory(d[:,::-1],w,groups,8)
