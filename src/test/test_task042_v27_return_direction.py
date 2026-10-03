"""Bounded return-path algebra and isolated one-run regression, no real window."""
from collections import Counter
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.linalg import lu_factor, lu_solve, lstsq

from src.solvers.return_block_direction import (
    FAMILY,NAMES,OUTER_BLOCKS,SelectedBundle,return_direction,extend_nine,decision,
)
from src.solvers.neural_fe_action_packet import array_hash,file_hash
from src.solvers.bounded_diagnostic_window import DiagnosticWindow
from src.test.test_task042_v22_p1_trace import dense_case


def test_real_nonhermitian_nonmutual_40port_chain_cancel_rank_linear_zero():
    packet,bar,z,A,*_=dense_case(n=16)
    ids=np.array([0,2,4,6,8,10,12,14]);outside=np.setdiff1d(np.arange(16),ids)
    factor=lu_factor(A[np.ix_(ids,ids)])
    def build(r):
        qj=np.zeros(16,complex);qj[ids]=lu_solve(factor,r[ids])
        aq=bar.apply(qj);w=np.zeros(16,complex)
        for rows in np.array_split(outside,2):w[rows]=np.linalg.solve(A[np.ix_(rows,rows)],aq[rows])
        return return_direction(qj,w,lambda x:lu_solve(factor,x),ids,bar.apply)
    r=bar.reduced_rhs(packet.a['b'])-bar.apply(.3*z[:16]);flow=build(r)
    np.testing.assert_allclose(flow['image'][ids],0,atol=1e-12)
    np.testing.assert_allclose(flow['return_image'][ids],r[ids],atol=1e-12)
    np.testing.assert_allclose(flow['image'],A@flow['direction'],atol=1e-12)
    a=.31+.42j;np.testing.assert_allclose(build(a*r)['return_direction'],a*flow['return_direction'],atol=1e-12)
    external=np.zeros(16,complex);external[outside]=1+.8j
    np.testing.assert_array_equal(build(external)['return_direction'],np.zeros(16,complex))
    np.testing.assert_array_equal(build(np.zeros(16,complex))['return_direction'],np.zeros(16,complex))
    t=.3*z[:16];full=bar.close(t,packet.a['b'])
    assert full.shape==(56,) and np.linalg.norm(full[-40:])>0
    assert np.linalg.norm(packet.S[:16,-40:]-packet.S[-40:,:16].conj().T)>1
    correction=bar.close(flow['direction'],np.zeros(packet.size,complex))
    np.testing.assert_allclose(packet.recover(full+correction)-packet.recover(full),
        packet.recover(correction)-packet.recover(np.zeros(packet.size,complex)),atol=1e-12)


def test_outer_amplification_counterexample_is_not_assumed_contractive():
    A=np.array([[1.,2.],[3.,1.]],complex);qj=np.array([1.,0.],complex);w=np.array([0.,3.],complex)
    out=return_direction(qj,w,lambda x:x,np.array([0]),lambda x:A@x)
    np.testing.assert_array_equal(out['return_direction'],[7,-3])
    np.testing.assert_array_equal(out['return_image'],[1,18])
    assert abs(out['return_image'][1])==6*abs((A@qj)[1])
    # The scale callback runs immediately after its corresponding action.
    touched=[]
    def action(x):touched.append(x.copy());return A@x
    def scale(x):np.testing.assert_array_equal(x,touched[-1]);return np.linalg.norm(A)*np.linalg.norm(x)
    out=return_direction(qj,w,lambda x:x,np.array([0]),action,scale)
    assert set(out['action_operation_scales'])=={'w','d','feedback','qret'}


def thin_case(kind):
    n=16;Q9=np.eye(n,9,dtype=complex);W9=Q9.copy();r=np.ones(n,complex)*(1+.4j)
    d=np.eye(n,dtype=complex)[:,9]
    if kind=='duplicate':d=Q9[:,0]*(.5+.3j)
    if kind=='zero':d[:]=0
    if kind=='nearzero':d*=1e-200
    if kind=='solved_baseline':r[9:]=0
    c9=r[:9];e9=r-W9@c9;count=Counter()
    row,arrays=extend_nine(r,Q9,W9,c9,e9,d,d,lambda x:x,bnorm=10,
        old_scales=np.ones(9),new_scale=1.,count=lambda k,n=1:count.update({k:n}))
    return row,arrays,count,r,Q9,d


def test_one_thin_workflow_matches_independent_complex_ls():
    row,a,c,r,Q,d=thin_case('new')
    coef=lstsq(np.column_stack((Q,d)),r,cond=1e-12,lapack_driver='gelsd')[0]
    assert row['trustworthy'] and row['new_direction_resolved'] and row['rank']==10
    np.testing.assert_allclose(a['diagnostic_residual'],r-np.column_stack((Q,d))@coef,atol=1e-14)
    assert c==Counter(thin_decompositions=1)
    assert row['eta10']<=row['eta9'] and row['independent_recombination']['operation_relative']<1e-14


@pytest.mark.parametrize('kind',['duplicate','zero','nearzero'])
def test_redundant_zero_nearzero_never_saved_with_huge_new_coefficient(kind):
    row,a,c,*_=thin_case(kind)
    assert not row['new_direction_resolved'] and a['coefficients'][-1]==0
    assert row['status'] in ('REDUNDANT_OR_UNRESOLVED','NUMERICALLY_UNRESOLVED')
    assert c['thin_decompositions']==1


def test_zero_baseline_not_positive_and_original_action_gate_independent():
    row,a,*_=thin_case('solved_baseline');assert row['g10'] is None
    n=16;Q=np.eye(n,9,dtype=complex);r=np.ones(n,complex);d=np.eye(n,dtype=complex)[:,9]
    row,a=extend_nine(r,Q,Q,r[:9],r-Q@r[:9],d,d,lambda x:1.01*x,
        bnorm=10,old_scales=np.ones(9),new_scale=1.)
    assert not row['trustworthy'] and not row['gates']['original_recombination']


def test_named_two_state_inventory_and_fixed_thresholds():
    def rows(g,resolved=True):return [dict(name=n,trustworthy=True,new_direction_resolved=resolved,g10=g) for n in NAMES]
    assert decision(rows(.7))=='RETURN_EXTRA_DIRECTION_SIGNAL'
    assert decision(rows(.96))=='FIXED_RETURN_DIRECTION_INSUFFICIENT'
    assert decision(rows(.8))=='STATE_DEPENDENT_INCONCLUSIVE'
    assert decision(rows(.96,False))=='REDUNDANT_OR_UNRESOLVED'
    assert decision([])==decision(rows(.7)[:1])=='NUMERICALLY_UNRESOLVED'
    duplicated=rows(.7);duplicated[1]['name']=duplicated[0]['name'];assert decision(duplicated)=='NUMERICALLY_UNRESOLVED'


def bundle_item(folder):
    folder.mkdir(exist_ok=True);A=np.array([[2+1j,.3-.7j],[-.8+.2j,3-.5j]])
    LU,piv=lu_factor(A);out=dict(rows=[0,2])
    for name,value in [('matrix',A),('LU',LU),('pivots',piv)]:
        p=folder/(name+'.npy');np.save(p,value)
        out[name]=dict(path=str(p),sha256=file_hash(p),array_sha256=array_hash(value),shape=list(value.shape))
    return A,out


def test_readonly_one_bundle_private_pivot_two_witness_two_actual_rhs(tmp_path):
    A,item=bundle_item(tmp_path);counts=Counter()
    reader=SelectedBundle(item,tmp_path,kind='outer',count=lambda k,n=1:counts.update({k:n}))
    try:
        assert reader.witnesses((422401,422402))['qualified']
        for v in [np.array([1+.2j,.3j]),np.array([-.7j,1+2j])]:
            np.testing.assert_allclose(A@reader.solve(v),v,atol=1e-14)
        assert counts==Counter(factor_readers=1,outer_lu_solve=4,explicit_triangular_pass=8)
        assert reader.pivots.flags.writeable and not reader.LU.flags.writeable
        assert all(x['numeric_mmap_loads']==1 and not x['full_hash_copy'] for x in reader.receipts)
        with pytest.raises(ValueError,match='one vector'):reader.solve(np.ones((2,2)))
    finally:reader.close()
    assert reader.loaded==[]


@pytest.mark.parametrize('bad',['hash','path','order','array_hash','shape'])
def test_reader_rejects_before_numeric_consumption(tmp_path,bad):
    _,item=bundle_item(tmp_path/'ok')
    if bad=='hash':item['LU']['sha256']='0'*64
    if bad=='path':item['matrix']['path']=str(tmp_path/'missing.npy')
    if bad=='order':item['rows']=[2,0]
    if bad=='array_hash':item['matrix']['array_sha256']='0'*64
    if bad=='shape':item['matrix']['shape']=[3,3]
    with pytest.raises(ValueError):SelectedBundle(item,tmp_path/'ok',kind='outer')


@pytest.fixture
def schema(monkeypatch,tmp_path):
    from src.io import return_block_diagnostic as io
    from src.solvers import return_block_window as module
    from src.io.task042_profile import TASK042_PROFILES
    from src.solvers.exact_recycle_window import evaluate_window
    own=dict(action_sha256='1'*64,physical_sha256='2'*64,states=[dict(name=n) for n in NAMES],
        joint_blocks=[5,7],outer_blocks=list(OUTER_BLOCKS),joint_rows=3888)
    plan=tmp_path/'plan.json';plan.write_text(json.dumps(own));monkeypatch.setattr(io,'PLAN_PATH',plan)
    design=dict(geometry={},incidence={},finite_element={},boundary={})
    material=SimpleNamespace(provenance=dict(material_table_id='SI_OPTICAL_CONSTANTS_USER_20260929_V1'))
    monkeypatch.setattr(io,'plan_and_operator',lambda:(dict(physical_model_sha256=own['physical_sha256']),design,material,dict(packet=dict(sha256=own['action_sha256']))))
    w=DiagnosticWindow(tmp_path,module.CAPS,'V27');monkeypatch.setattr(module,'_window',w)
    for key in ('ledger','require_live','auxiliary_wall'):monkeypatch.setattr(module,key,getattr(w,key))
    frozen=dict(start_utc='2026-01-01T00:00:00Z',start_monotonic=100,boot_id='fixture',heavy_limit_seconds=4500,total_limit_seconds=5400)
    clock=dict(utc=1767225700.,monotonic=200.)
    monkeypatch.setattr(w,'snapshot',lambda:evaluate_window(frozen,utc_seconds=clock['utc'],monotonic=clock['monotonic'],boot_id='fixture'))
    return io,w,clock,TASK042_PROFILES


def test_actual_dat_registration_dispatch_and_original_dat_unchanged(schema):
    io,w,clock,profiles=schema
    spec=io.load_return_diagnostic('input/task042_neural_coarse_inverse/v27_return_direction_diagnostic.dat')
    assert profiles[spec.solver['preconditioner']]=='V27-DIAGNOSTIC'
    assert spec.derived['environment_mode']=='pure' and spec.execution['mpi_size']==1
    assert io.load_return_diagnostic('input/task042_neural_coarse_inverse/v26_joint_block_diagnostic.dat') is None
    s=Path('scripts/run_case.py').read_text();adapter=Path('src/runners/task042_shared.py').read_text()
    assert 'load_return_diagnostic(args.input_path)' in s and 'src.runners.return_block_diagnostic' in adapter


@pytest.mark.parametrize('bad',['active','closed','consumed','expired','aux_exhausted'])
def test_real_ledger_and_time_rejections_are_isolated(schema,bad):
    io,w,clock,_=schema;book=w.ledger()
    if bad=='active':book['active']={}
    if bad=='closed':book['closed']=True
    if bad=='consumed':book['runs']=[{}]
    if bad=='expired':clock.update(utc=1767225700.+5500,monotonic=5700.)
    if bad=='aux_exhausted':
        p=w.TMP/'aux_1';p.mkdir();(p/'summary.json').write_text(json.dumps(dict(elapsed_seconds=601)))
    w.LEDGER_PATH.write_text(json.dumps(book))
    from src.io.input_loader import InputError
    with pytest.raises(InputError):io.load_return_diagnostic('input/task042_neural_coarse_inverse/v27_return_direction_diagnostic.dat')


def test_limits_refuse_reader_rhs_decomposition_or_action_overrun(tmp_path):
    from src.solvers.return_block_window import CAPS
    w=DiagnosticWindow(tmp_path,CAPS,'V27')
    charged=dict.fromkeys(CAPS,0)
    for key in CAPS:
        completed=charged.copy();completed[key]=CAPS[key]
        with pytest.raises(RuntimeError):w.validate_increment(charged,completed,key)
    with pytest.raises(RuntimeError):w.validate_increment(charged,charged,'unknown')
