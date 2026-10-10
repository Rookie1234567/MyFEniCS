"""Necessary-condition diagnostics with manufactured and corrupt controls."""

import json
import numpy as np
import pytest

from src.solvers.ftt_capacity import (
    unfold, full_spectrum, rank_bound, necessary_ranks,
    axis_project, feature_bound, decision,
)
from src.solvers.ftt_capacity_checks import algebra_checks


def spectra(tensors):
    return {s: [full_spectrum(T, a)[1] for a in range(3)] for s, T in tensors.items()}


def test_known_complex_rank_eight_and_high_rank_are_distinguished():
    result = algebra_checks()
    assert result["qualified"]
    assert result["known_rank8"]["conservative_relative_lower_estimate"] < 1e-12
    assert result["known_rank12"]["conservative_relative_lower_estimate"] > .5
    assert result["no_bridge_negative"] == "NO_VALID_FE_CAPACITY_CERTIFICATE"


def test_tail_max_does_not_add_overlapping_axis_errors():
    T = np.zeros((12,12,12), dtype=np.complex128)
    T[np.arange(12),np.arange(12),np.arange(12)] = 1+2j
    values = spectra({s:T for s in "xyz"})
    bound = rank_bound(values, [8,8,8], 10)
    assert bound["conservative_relative_lower_estimate"] == pytest.approx(np.sqrt(60)/10)
    assert bound["conservative_relative_lower_estimate"] != pytest.approx(np.sqrt(180)/10)
    # The full field also contains an orthogonal remainder: its norm is NOT
    # the internal moment norm. This changes a valid relative bound.
    wider = rank_bound(values, [8,8,8], 20)
    assert wider["conservative_relative_lower_estimate"] == pytest.approx(bound["conservative_relative_lower_estimate"]/2)


def test_measured_perturbation_cannot_strengthen_exclusion():
    T = np.eye(12,dtype=np.complex128)[:,:,None]*np.ones((1,1,2))
    values = spectra({s:T for s in "xyz"})
    a=rank_bound(values,[8,8,1],20)
    b=rank_bound(values,[8,8,1],20,input_defect=1)
    assert b["conservative_relative_lower_estimate"]<a["conservative_relative_lower_estimate"]
    assert b["numerical_margin"]>=a["numerical_margin"]


def test_axis_layout_and_conjugate_negative_controls():
    rng=np.random.default_rng(40)
    T=(rng.normal(size=(4,5,6))+1j*rng.normal(size=(4,5,6))).astype(np.complex128)
    Q=np.linalg.qr(rng.normal(size=(5,2))+1j*rng.normal(size=(5,2)))[0]
    expected=np.einsum('ab,ibk->iak',Q@Q.conj().T,T)
    assert np.linalg.norm(axis_project(T,Q,1)-expected)<1e-12
    assert np.linalg.norm(expected-np.einsum('ab,ibk->iak',Q@Q.T,T))>.1
    with pytest.raises(ValueError,match='LAYOUT'):
        axis_project(T,Q,0)
    with pytest.raises(ValueError,match='AXIS'):
        unfold(T,3)


def test_rank_is_necessary_not_sufficient_and_fe_bridge_required():
    empty={"exceeds_gate_and_margin":False}
    assert decision({"rank_bound_transferable_to_actual_FE":True},empty,empty,{}) == 'REPRESENTATION_NOT_EXCLUDED_OPTIMIZATION_UNRESOLVED'
    excluded={"exceeds_gate_and_margin":True}
    assert decision({},excluded,excluded,{}) == 'NO_VALID_FE_CAPACITY_CERTIFICATE'
    assert decision({"rank_bound_transferable_to_actual_FE":True},excluded,empty,{}) == 'R8_CAPACITY_EXCLUDED_NUMERICALLY'


def test_necessary_rank_from_full_spectrum_no_training():
    T=np.zeros((12,12,12),np.complex128)
    T[np.arange(12),np.arange(12),np.arange(12)]=np.arange(12,0,-1)
    result=necessary_ranks(spectra({s:T for s in "xyz"}),30)
    assert all(r==12 for r in result['0.0001']['x'])


def test_full_feature_projection_retains_small_nonzero_directions():
    rng=np.random.default_rng(41)
    T=(rng.normal(size=(3,3,3))+1j*rng.normal(size=(3,3,3))).astype(np.complex128)
    complete={s:[np.eye(3,dtype=np.complex128)]*3 for s in "xyz"}
    complete_bound=feature_bound({s:T for s in "xyz"},complete,20)
    reduced={s:[np.eye(3,dtype=np.complex128)[:,:2]]*3 for s in "xyz"}
    assert complete_bound['relative_lower_estimate']<1e-12
    assert feature_bound({s:T for s in "xyz"},reduced,20)['relative_lower_estimate']>.01
    # A larger error after deleting a tiny nonzero feature cannot be promoted
    # to a necessary lower bound for the complete original feature space.


def test_complex_svd_is_complete_and_backward_stable():
    rng=np.random.default_rng(42)
    T=(rng.normal(size=(5,6,7))+1j*rng.normal(size=(5,6,7))).astype(np.complex128)
    for a in range(3):
        (U,s,Vh),record=full_spectrum(T,a)
        assert record['qualified'] and len(s)==T.shape[a]
        assert np.linalg.norm((U*s)@Vh-unfold(T,a))<1e-12
    with pytest.raises(ValueError,match='COMPLEX128'):
        full_spectrum(T.real,0)


def test_physical_legendre_tests_are_l2_orthonormal_and_bessel():
    from itertools import product
    from src.solvers.ftt_interior_bridge import test_definition
    nodes,w=np.polynomial.legendre.leggauss(4)
    points=np.array(list(product((nodes+1)/2,repeat=3)))
    weights=np.array([np.prod(item) for item in product(w/2,repeat=3)])
    _,components,values=test_definition(points)
    gram=(values.T*weights)@values
    for component in range(3):
        ids=components==component
        assert np.linalg.norm(gram[np.ix_(ids,ids)]-np.eye(12))<1e-12


def test_saved_checker_corrupted_array_hash_and_geometry_fail_closed(tmp_path,monkeypatch):
    import benchmarks.check_ftt_capacity as checker
    path=tmp_path/'data.npz'
    np.savez(path,c=np.ones(4))
    monkeypatch.setattr(checker,'ROOT',tmp_path)
    with pytest.raises(ValueError,match='HASH'):
        checker.read_arrays({'path':'data.npz','sha256':'0'*64})


def test_capacity_schema_and_campaign_use_unique_window_and_roles():
    from src.io.neural_wave_campaign import load_wave,profile_paths
    from src.runners.neural_wave_campaign import window,stage_deadline
    from src.runners.block_wave_admission import wait_limit
    spec=load_wave('input/task042extra_feinn_5nm/v40_rank_and_feature_bounds.dat')
    assert spec['campaign_version']==40 and spec['mode']=='ml'
    assert profile_paths(spec)['artifacts'].name=='v40'
    w=window(spec)
    assert w['budget_s']==14400 and w['original_origin_preserved']
    assert stage_deadline(spec,{'deadline_monotonic':w['deadline_monotonic']},w)[0]==w['deadline_monotonic']-1800
    assert wait_limit(profile_paths(spec)['root'])==900


@pytest.fixture
def saved_fixture(tmp_path,monkeypatch):
    import benchmarks.check_ftt_capacity as checker
    from src.io.neural_wave_campaign import digest
    monkeypatch.setattr(checker,'ROOT',tmp_path)
    for folder in ('v40_interior_moment_tensor','v40_rank_and_feature_bounds'):
        (tmp_path/folder).mkdir()
    def write(relative,value):
        path=tmp_path/relative
        path.write_text(json.dumps(value))
        return {'path':relative,'sha256':digest(path)}
    def save(relative,value):
        path=tmp_path/relative
        np.savez(path,**value)
        return {'path':relative,'sha256':digest(path)}
    rng=np.random.default_rng(4214001)
    tensors={s:(rng.normal(size=(8,6,8))+1j*rng.normal(size=(8,6,8))).astype(np.complex128) for s in 'xyz'}
    norm=np.sqrt(sum(np.linalg.norm(t)**2 for t in tensors.values())+3)
    norm_entry=write('norm.json',{'physics':{'reference_scattered_norms':[norm]}})
    bridge={'arrays':save('T.npz',{k+'_'+s:t for k in ('full','independent') for s,t in tensors.items()}),
            'original_full_scattered_E_denominator':norm,'reference_E_norm':norm,
            'input_identity':{'norm_record':norm_entry},'full_E_norm_independent_pass':True,
            'max_functional_transform_relative':1e-15,'original_J_non_diagonal_max_nm':1e-15,
            'original_axis_origin_or_width_nonseparability_max_nm':1e-15,
            'rank_bound_transferable_to_actual_FE':False,'original_J_was_zeroed':False}
    sr={'spectra':{},'bounds':{}}
    S={}
    for s,T in tensors.items():
        sr['spectra'][s]=[]
        for axis in range(3):
            (U,sigma,Vh),record=full_spectrum(T,axis)
            sr['spectra'][s].append(record)
            for name,value in (('U',U),('s',sigma),('Vh',Vh)):
                S[f'{s}_{axis}_{name}']=value
    sr['arrays']=save('S.npz',S)
    sr['bounds']={name:rank_bound(sr['spectra'],r,norm) for name,r in [('pure_r8',[8,64,8]),('width16',[8,17,8]),('cheb19',[8,19,8])]}
    bases={s:[np.eye(n,dtype=np.complex128) for n in (8,6,8)] for s in 'xyz'}
    record=feature_bound(tensors,bases,norm)
    record.update(axis_feature_records={s:[{'discarded_nonzero_columns':0} for _ in range(3)] for s in 'xyz'},
                  pde_only_solve=False,production_initialization_allowed=False,
                  actual_FE_certificate=False,finite_chart_full_space_qualified=True)
    Fs={f'native_final_{kind}_{axis}_0':np.eye(n) for kind in ('F','Q') for axis,n in enumerate((8,6,8))}
    fr={'arrays':save('F.npz',Fs),'records':{'native_final':record}}
    write('v40_interior_moment_tensor/interior_tensor.json',bridge)
    write('v40_rank_and_feature_bounds/spectra.json',sr)
    write('v40_rank_and_feature_bounds/features.json',fr)
    return tmp_path,bridge,sr,fr,write


def test_independent_saved_checker_recomputes_limited_scientific_exit(saved_fixture):
    from benchmarks.check_ftt_capacity import check_saved
    root,*_=saved_fixture
    record=check_saved(root)
    assert record['qualified_saved_numeric_consistency']
    assert record['decision']=='NO_VALID_FE_CAPACITY_CERTIFICATE'


@pytest.mark.parametrize('bad_kind',['normalization','tail','truncation','production','geometry','actual_feature_promotion'])
def test_corrupted_saved_records_not_trusted_even_with_updated_json(saved_fixture,bad_kind):
    from benchmarks.check_ftt_capacity import check_saved
    root,bridge,sr,fr,write=saved_fixture
    if bad_kind=='normalization':
        bridge['original_full_scattered_E_denominator']*=2
    elif bad_kind=='tail':
        sr['bounds']['pure_r8']['conservative_relative_lower_estimate']=.5
    elif bad_kind=='truncation':
        fr['records']['native_final']['axis_feature_records']['x'][0]['discarded_nonzero_columns']=1
    elif bad_kind=='production':
        fr['records']['native_final']['production_initialization_allowed']=True
    elif bad_kind=='geometry':
        bridge['rank_bound_transferable_to_actual_FE']=True
    else:
        fr['records']['native_final']['actual_FE_certificate']=True
    write('v40_interior_moment_tensor/interior_tensor.json',bridge)
    write('v40_rank_and_feature_bounds/spectra.json',sr)
    write('v40_rank_and_feature_bounds/features.json',fr)
    with pytest.raises(ValueError,match='CAPACITY_'):
        check_saved(root)


@pytest.mark.parametrize('ranks,denominator,defect', [([8,8],1,0),([8,8,8],0,0),([8,8,8],1,-1)])
def test_invalid_bound_metadata_rejected(ranks,denominator,defect):
    with pytest.raises(ValueError):
        rank_bound({},ranks,denominator,defect)


@pytest.mark.parametrize('bad_kind', ['margin', 'rank', 'backward'])
def test_checker_recomputes_rank_and_numerical_margin(saved_fixture,bad_kind):
    from benchmarks.check_ftt_capacity import check_saved
    root,_,sr,_,write=saved_fixture
    if bad_kind=='margin':
        sr['bounds']['pure_r8']['numerical_margin']=0
    elif bad_kind=='rank':
        sr['bounds']['pure_r8']['ranks']=[7,64,8]
    else:
        sr['spectra']['x'][0]['backward_error_numerator']=.1
    write('v40_rank_and_feature_bounds/spectra.json',sr)
    with pytest.raises(ValueError,match='CAPACITY_'):
        check_saved(root)


@pytest.mark.parametrize('bad_kind', ['none', 'erase_geometry', 'axis', 'design_hash'])
def test_checker_reads_original_geometry_arrays(saved_fixture,bad_kind):
    from benchmarks.check_ftt_capacity import check_saved
    from src.io.neural_wave_campaign import digest
    root,bridge,_,_,write=saved_fixture
    ids=np.indices((8,6,8)).reshape(3,-1).T
    J=np.tile(np.eye(3)[None,:,:]*1.25,(384,1,1))
    J[:,0,1]=1e-15
    packet=root/'packet.npz'
    np.savez(packet,jacobians=J,origins=ids*1.25)
    frozen=write('design.json',{'files':{'moments_q30':{'path':'packet.npz','sha256':digest(packet)}},
                              'model':{'geometry':{'cells':[8,6,8]}}})
    bridge['original_axis_origin_or_width_nonseparability_max_nm']=0
    Tpath=root/bridge['arrays']['path']
    with np.load(Tpath) as saved:
        T={k:np.array(saved[k]) for k in saved.files}
    T['axis_ids']=ids
    if bad_kind=='erase_geometry':
        bridge['original_J_non_diagonal_max_nm']=0
        bridge['rank_bound_transferable_to_actual_FE']=True
    elif bad_kind=='axis':
        T['axis_ids'][0]=T['axis_ids'][1]
    elif bad_kind=='design_hash':
        frozen['sha256']='0'*64
    np.savez(Tpath,**T)
    bridge['arrays']['sha256']=digest(Tpath)
    write('v40_interior_moment_tensor/interior_tensor.json',bridge)
    if bad_kind=='none':
        record=check_saved(root,frozen_design=frozen)
        assert record['original_geometry_array_check']['off_axis_max_nm']==1e-15
        assert not record['actual_FE_rank_bridge_qualified']
    else:
        with pytest.raises(ValueError,match='CAPACITY_'):
            check_saved(root,frozen_design=frozen)
