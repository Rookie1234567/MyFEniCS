"""Tiny complex overlap and compact streaming evidence; no FE/PETSc factor."""
import weakref
import numpy as np
import pytest
from src.runners.physical_diagnosis_worker import save_packet
from src.runners.physical_diagnostic_completion import load_packet
from src.solvers.physical_projected_trace import ProjectedTraceFactorStore,projected_local_oracle
from src.solvers.physical_trace_cell_patch import symmetric_patch_solve


def test_factor_only_overlap_streaming_and_legacy_isolation(tmp_path):
    indices=np.array([[0,1],[1,2]]);weights=1/np.sqrt([1,2,1]);offsets=np.array([0,1,3])
    store=ProjectedTraceFactorStore(indices,weights,offsets)
    matrices=[np.array([[3+.2j,.4-.1j],[.2+.3j,2-.1j]]),np.array([[2+.5j,-.3j],[.6,4+.1j]])]
    for i,matrix in enumerate(matrices):
        current=matrix.copy();ref=weakref.ref(current)
        store.append(current,save=lambda name,row:save_packet(tmp_path,f'{i}_{name}',row))
        del current
        assert ref() is None
    rhs=np.array([1+.2j,-.3+.5j,2-1j]);before=rhs.copy();expected=np.zeros(3,complex)
    for rows,D in zip(indices,matrices,strict=True):np.add.at(expected,rows,weights[rows]*np.linalg.solve(D,weights[rows]*rhs[rows]))
    result=np.concatenate(store.apply([rhs[:1],rhs[1:]],lambda:None))
    np.testing.assert_allclose(result,expected,rtol=1e-14,atol=1e-14);np.testing.assert_array_equal(rhs,before)
    assert store.last_facts['runtime_original_D_residual']=='not_measured'
    assert all(not hasattr(f,'D') for f in store.factors)
    legacy=[dict(D=D,factor=f.factor,members=np.array([i])) for i,(D,f) in enumerate(zip(matrices,store.factors,strict=True))]
    def gate(value):assert np.isfinite(value) and value<=1e-11
    old,_=symmetric_patch_solve(rhs,indices,weights,legacy,check=gate,sample=lambda:None)
    np.testing.assert_allclose(result,old,rtol=1e-14,atol=1e-14)
    del legacy[0]['D']
    with pytest.raises(KeyError):symmetric_patch_solve(rhs,indices,weights,legacy,check=gate,sample=lambda:None)
    with pytest.raises(ValueError):store.apply([np.full(3,np.nan)],lambda:None)

    class Cross:
        dimension=9;coarse_rows=2;saved_Q_rhs=0;seconds={'R':0.,'L':0.}
        def right(self,a,b):
            self.right_facts=dict(per_column_relative=np.zeros(b-a),limit=1e-11)
            return np.vstack([np.arange(a+1,b+1)*(.1+.02j),np.ones(b-a)*(.2-.03j)])
        def left(self,x):return np.arange(1,10)[:,None]*(.01+.03j)@np.sum(x,axis=0,keepdims=True)
        def retained_bytes(self):return 0
    cross=Cross();D=20*np.eye(9,dtype=complex);calls=[]
    def solve(rhs):
        calls.append(1);return rhs.copy(),dict(relative=0.,residual_absolute=0.,rhs_norm=float(np.linalg.norm(rhs)),refinement=0)
    value,_,facts=projected_local_oracle(cross,D,solve,save=lambda name,row:save_packet(tmp_path,name,row),save_success_arrays=False)
    R=cross.right(0,9);np.testing.assert_allclose(value,D-cross.left(R),atol=1e-14)
    assert len(calls)==9 and facts['blocks']==2
    record=load_packet(tmp_path/'block_000.json');assert not {'R','X','correction'}&record.keys()
    assert len(record['S_facts'])==8 and record['S_facts'][0]['rhs_norm']>0
    with pytest.raises(ValueError):
        projected_local_oracle(cross,D,lambda rhs:(rhs.copy(),dict(relative=1e-5)),
            save=lambda name,row:save_packet(tmp_path,'bad_'+name,row),save_success_arrays=False)
    failed=load_packet(tmp_path/'bad_column_000_failure.json')
    assert failed['solution'] is not None and failed['facts']['relative']==1e-5
