"""Small complex linear systems; no FE assembly or original-size runs."""
from types import SimpleNamespace

import numpy as np
import pytest
from petsc4py import PETSc

from src.solvers.condensed_fine_reference import (
    FineReferenceCapacityRejected,numeric_allowance,solve_and_release,residual_packet,relative_difference)


@pytest.mark.parametrize('extra,admitted',[(0,True),(-1,False),(1,True)])
def test_single_mb_allowance_and_512mib_reserve(extra,admitted):
    rss,future,estimate=1000,2000,4858
    cap=rss+future+512*1024**2+estimate*1_000_000+extra
    record=numeric_allowance(dict(rss_bytes=rss,launch_cap_bytes=cap),
        {'infog':{'16':estimate-1,'17':estimate}},future)
    assert (record['status']=='ADMISSIBLE') is admitted
    assert record['icntl23_mb']==estimate-(extra<0)
    assert record['engineering_reserve_bytes']==512*1024**2


def test_native_residual_rejects_small_augmented_residual_as_substitute():
    b=np.array([1+1j,2,0],complex);x=np.array([1,2j,0],complex)
    ax=b.copy();ax[1]+=1e-8
    packet=residual_packet(x,b,ax,np.array([2]))
    assert packet['status']=='REFERENCE_ACCURACY_UNRESOLVED'
    packet=residual_packet(x,b,b.copy(),np.array([2]))
    assert packet['status']=='REFERENCE_PASS'
    x[2]=1
    with pytest.raises(ValueError):residual_packet(x,b,b,np.array([2]))
    with pytest.raises(ValueError):relative_difference(np.array([np.nan]),np.ones(1))


@pytest.mark.parametrize('failure',[None,'capacity','numeric','save','cleanup'])
def test_one_numeric_two_solves_fixed_augmented_correction_and_release(failure):
    values=np.array([[3,1j,0],[1,4,1],[0,1,3]],complex)
    matrix=PETSc.Mat().createAIJ((3,3),nnz=3,comm=PETSc.COMM_SELF)
    matrix.setValues(range(3),range(3),values);matrix.assemble()
    b=matrix.createVecRight();b.array[:]=[1j,2,3-1j]
    events=[];packets={};returned=()
    class Factor:
        def symbolic(self,a):events.append('symbolic')
        def info(self,indices):return {'infog':{'16':1,'17':1}}
        def symbolic_memory_settings(self):return {'icntl':{},'modified':False}
        def set_memory_limit_mb(self,limit):events.append('limit');assert limit>0
        def numeric(self,a):
            events.append('numeric')
            if failure=='numeric':raise ValueError('numeric failure')
        def solve(self,rhs,x):
            events.append('solve');x.array[:]=np.linalg.solve(values,rhs.array)*(1+1e-6)
        def solve_repeated(self,rhs,x):
            events.append('correction');x.array[:]=np.linalg.solve(values,rhs.array)
        def destroy(self):
            events.append('destroy')
            if failure=='cleanup':raise RuntimeError('cleanup failure')
    def save(name,record):
        packets[name]={k:v.copy() if isinstance(v,np.ndarray) else v for k,v in record.items()}
        if name=='reference_augmented_initial' and failure=='save':raise OSError('packet failed')
    record=dict(identity={'test':True},cleanup_errors=[])
    request=SimpleNamespace(A=matrix,b=b,static_condensed_system=SimpleNamespace(
        full_rows=3,active_rows=2,appended_rows=1,interior_rows=1))
    def operation():return solve_and_release(request,record,
        sample=lambda:dict(rss_bytes=100,launch_cap_bytes=1 if failure=='capacity' else 2*1024**3),
        marker=lambda stage,facts:events.append(stage),save=save,factor_factory=lambda a:Factor())
    try:
        if failure is None:
            returned=operation();initial,corrected=returned
            assert events.count('numeric')==events.count('solve')==events.count('correction')==1
            assert events.index('destroy')<events.index('fine_reference_factor_released')
            assert record['solve_calls']==2 and record['correction_calls']==1
            assert record['augmented_relative_before']>1e-7
            assert record['augmented_relative_after']<1e-14
            assert np.linalg.norm(values@corrected.array-b.array)<1e-14
            np.testing.assert_array_equal(packets['reference_augmented_initial']['x'],initial.array)
        else:
            with pytest.raises((FineReferenceCapacityRejected,ValueError,OSError,RuntimeError)):operation()
            assert 'destroy' in events
            if failure=='capacity':assert 'numeric' not in events
            if failure=='save':assert 'correction' not in events
    finally:
        for value in returned:value.destroy()
        b.destroy();matrix.destroy()


def test_real_mumps_icntl23_one_factor_two_mat_solve():
    from src.solvers.fullspace_v17_p3_oracle import _MumpsFactor
    matrix=PETSc.Mat().createAIJ((3,3),nnz=3,comm=PETSc.COMM_SELF)
    matrix.setValues(range(3),range(3),np.array([[3,1j,0],[1,4,1],[0,1,3]],complex));matrix.assemble()
    b=matrix.createVecRight();b.array[:]=[1j,2,3];x=b.duplicate();r=b.duplicate();d=b.duplicate();factor=None
    try:
        factor=_MumpsFactor(matrix);factor.symbolic(matrix)
        initial=factor.symbolic_memory_settings()['icntl']
        factor.set_memory_limit_mb(512)
        changed=factor.symbolic_memory_settings()['icntl']
        assert changed['23']==512
        assert all(changed[k]==v for k,v in initial.items() if k!='23')
        factor.numeric(matrix);factor.solve(b,x)
        matrix.mult(x,r);r.aypx(-1,b);factor.solve_repeated(r,d);x.axpy(1,d)
        matrix.mult(x,r);r.aypx(-1,b)
        assert r.norm()/b.norm()<1e-14
        assert factor.numeric_calls==1 and factor.solve_calls==2
    finally:
        if factor is not None:factor.destroy()
        for value in (x,r,d,b,matrix):value.destroy()
