import numpy as np
import pytest

from src.solvers.local_trace_features import boxes,local_coordinates,patch_ids,polynomial_features,extension_field
from src.solvers.local_trace_decoder import BlockTraceDecoder,UnionTraceDecoder,matched_local_spaces,complementary_space


def test_periodic_master_and_cut_ties_use_whole_entity_center():
    bounds=np.array([[-.7,.7],[-.525,.525],[-.175,1.225]])
    centers=np.array([[0,0,.525],[.7,.525,.525],[-.35,-.2,.2],[.35,.2,.9]])
    ids,representatives=patch_ids(centers,bounds)
    assert ids.tolist()==[0,0,0,7]
    np.testing.assert_allclose(representatives[1],[-.7,-.525,.525])
    assert centers[1,0]==.7  # Original integration entity is not rewritten.


def test_local_coordinates_and_fixed_65_polynomial_inventory():
    b=boxes([[-.7,.7],[-.525,.525],[-.175,1.225]])
    assert b.shape==(8,3,2)
    np.testing.assert_allclose(local_coordinates(b[0].T,b[0]),[[-1,-1,-1],[1,1,1]])
    values=polynomial_features(np.array([[0.,0.,0.],[1.,1.,1.]]))
    assert values.shape==(2,65)
    assert np.all(values[:,0]==1)
    assert values[0,-1]==pytest.approx(3/8)
    assert np.all(values[1]==1)


def test_extension_integrates_full_entity_beyond_box_without_mask():
    coefficient=np.zeros((3,65),complex);coefficient[1,0]=1+2j
    points=np.array([[-.3,0,.525],[.3,0,.525]])
    field=extension_field(points,np.array([[-.7,0],[-.525,0],[-.175,.525]]),np.array([2.,0.,-.1]),coefficient,polynomial_features)
    np.testing.assert_allclose(field[:,1],(1+2j)*np.exp(1j*(points@np.array([2.,0.,-.1]))))
    assert np.count_nonzero(field[:,1])==2


def decoder_fixture():
    rng=np.random.default_rng(6)
    rows=[np.arange(0,12,2),np.arange(1,12,2)]
    blocks=[np.linalg.qr(rng.standard_normal((6,3))+1j*rng.standard_normal((6,3)))[0] for _ in rows]
    return BlockTraceDecoder(rows,blocks,12)


def test_complex_block_forward_adjoint_and_column_match_explicit_matrix():
    d=decoder_fixture();rng=np.random.default_rng(9)
    explicit=np.column_stack([d.column(j) for j in range(d.shape[1])])
    c=rng.standard_normal(6)+1j*rng.standard_normal(6)
    t=rng.standard_normal(12)+1j*rng.standard_normal(12)
    np.testing.assert_allclose(d@c,explicit@c,atol=1e-14)
    np.testing.assert_allclose(d.adjoint(t),explicit.conj().T@t,atol=1e-14)
    check=d.identity_checks()
    assert max(check['forward_relative'],check['adjoint_operation_relative'],check['orthogonality'])<1e-10


def test_missing_duplicate_rows_and_empty_rank_rejected():
    with pytest.raises(ValueError,match='missing/duplicate'):
        BlockTraceDecoder([np.array([0,0])],[np.eye(2,dtype=complex)],2)
    with pytest.raises(ValueError,match='numerical rank'):
        BlockTraceDecoder([np.array([0,1])],[np.empty((2,0),complex)],2)


def test_capacity_matches_per_patch_minimum_without_rank_padding():
    rng=np.random.default_rng(10);rows=[np.arange(210),np.arange(210,420)]
    poly=[rng.standard_normal((210,195)).astype(complex) for _ in rows]
    neural=[p.copy() for p in poly]
    neural[0][:,180:]=neural[0][:,:15]
    counts=[]
    d,record=matched_local_spaces({'POLY':poly,'NN':neural},rows,420,lambda k:counts.append(k))
    assert record['common_rank_by_patch'].tolist()==[180,195]
    assert d['POLY'].shape==d['NN'].shape==(420,375)
    assert len(counts)==4
    assert not record['rank_padding']


def test_union_keeps_global_space_and_reorthogonalizes_complement():
    local=decoder_fixture();rng=np.random.default_rng(7)
    G=np.linalg.qr(rng.standard_normal((12,3))+1j*rng.standard_normal((12,3)))[0]
    U,record=complementary_space(G,local)
    union=UnionTraceDecoder(G,U)
    assert union.orthogonality()<1e-10
    c=rng.standard_normal(3)+1j*rng.standard_normal(3)
    np.testing.assert_allclose(union@np.r_[c,np.zeros(U.shape[1])],G@c,atol=1e-14)
    assert record['reorthogonalizations']==1
    assert not record['full_square_projection_constructed']


def test_duplicate_global_directions_give_no_new_complement():
    q=np.eye(5,dtype=complex)[:,:2]
    local=BlockTraceDecoder([np.arange(5)],[q],5)
    U,record=complementary_space(q,local)
    assert U.shape==(5,0) and record['raw_q']==0
