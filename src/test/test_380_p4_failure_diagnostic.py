"""Tiny array fixtures for the fixed p4 diagnostic orchestration only."""
import numpy as np
import pytest
import json
from pathlib import Path
from src.runners.physical_recursive_controls import measure_p4_failure, load_p4_failure_input
from src.runners.physical_recursive_entry import p4_bridge_status
from src.runners.physical_diagnosis_worker import save_packet
from src.runners.physical_diagnostic_completion import load_packet


def fixture_run(*, timeout=False, corrupt=False, save=None):
    matrix=np.diag([2.,3.]).astype(complex)
    y=np.array([1.,2.],complex);g=matrix@y;c=y/4
    data=dict(binding={},scale=1.,arrays=dict(y=y,g=g,c=c,eps=g-matrix@c,A4y=g.copy()))
    if corrupt:data['arrays']['A4y'][0]+=1
    counts=dict(A=0,H=0,B=0,S=0);packets={}
    def A(x):counts['A']+=1;return matrix@x
    def H(x):counts['H']+=1;return x/4
    def B(x):counts['B']+=1;return x/4
    def S(x):counts['S']+=1;return x/2
    def diagonal(checkpoint):checkpoint();return np.array([1.])
    def record(n,v):
        packets[n]=v
        if save:save(n,v)
    result=measure_p4_failure(data,A=A,P=lambda x:np.array([x[0],0j]),PH=lambda x:x[:1].copy(),
        M=lambda x:x.copy(),curl=lambda x:2*x,diagonal=diagonal,solve2=S,H4=H,B4=B,
        sample=lambda:None,save=record,projection_seconds=lambda start=False:601 if timeout else 0,
        components={'curl':lambda x:matrix@x,'material_mass':lambda x:0*x,'dtn':lambda x:0*x},
        b4_facts=lambda:dict(counts={'C':2},operation_seconds={'C':0.1}))
    return result,counts,packets


def test_fixed_sequence_and_component_closure():
    result,counts,p=fixture_run()
    assert counts==dict(A=9,H=1,B=2,S=2)
    assert result['I4_calls']==result['outer_calls']==0
    assert p['p2_projection']['status']=='PROJECTION_CLOSED'
    assert p['perpendicular_components']['sum_relative_error']==0
    assert p['B4_on_g']['B4_facts']['counts']['C']==2
    assert set(p['field_norms']['old_error'])=={'M0_squared','scaled_curl_squared'}


def test_projection_timeout_keeps_independent_controls():
    result,counts,p=fixture_run(timeout=True)
    assert result['projection_status']=='PROJECTION_UNRESOLVED'
    assert p['range_identity']['status']=='NOT_APPLICABLE_ZERO_RANGE'
    assert p['coarse_decomposition']['status']=='NOT_QUALIFIED_PROJECTION_UNRESOLVED'
    assert counts==dict(A=7,H=1,B=2,S=1)


def test_failed_bridge_is_saved_but_never_pass(tmp_path):
    path=tmp_path/'input_bridge.json'
    assert p4_bridge_status(path)=='NOT_REACHED'
    with pytest.raises(ValueError,match='physical bridge'):
        fixture_run(corrupt=True,save=lambda n,v:save_packet(tmp_path,n,v))
    assert p4_bridge_status(path)=='FAIL'
    fixture_run(save=lambda n,v:save_packet(tmp_path,n,v))
    assert p4_bridge_status(path)=='PASS'
    vectors=load_packet(path)['vectors']
    assert set(vectors)=={'g','y','A4y','c','eps'}
    np.testing.assert_array_equal(vectors['g'],vectors['A4y'])
    np.testing.assert_array_equal(vectors['eps'],vectors['g']*.75)


def test_frozen_binding_loads_exact_first_sample():
    path=Path('input/task39extra/p4_failure_diagnostic_v6.json')
    binding=json.loads(path.read_text())
    if any(not Path(p['path']).exists() for p in binding['packets'].values()):
        pytest.skip('local ignored calibration artifacts unavailable')
    data=load_p4_failure_input(path)
    assert data['binding']['sample']=='A2R160_BAL_H_p4_01'
    assert np.isclose(np.linalg.norm(data['arrays']['g']),1)
    assert all(np.isfinite(v).all() for v in data['arrays'].values())
