"""Bounded symbolic observation and cleanup; no original-size PDE."""
import copy
from types import SimpleNamespace

import numpy as np
import pytest

from src.solvers.condensed_reference_preflight import (
    CondensedPreflightExit, CondensedSymbolicPreflight, retained_payload)


def system():
    identity=np.eye(2)
    return SimpleNamespace(
        interior_from_trace_by_class={}, interior_lu_by_class={'a':(identity,identity[0])},
        interior_rhs_projection_by_class={'a':identity},
        interior_solution_embedding_by_class={'a':identity},
        trace_from_interior_rhs_by_class={}, interior_residual_projection_by_class={},
        cell_recovery_maps=(), trace_constraints={}, owned_trace_original_dofs=np.zeros(0),
        retained_local_schur_by_class=None, build_audit={},
        full_rows=173802, active_rows=51192, appended_rows=80, interior_rows=113400)


def test_distinct_payload_counts_views_and_identity_aliases_once():
    value=system()
    assert retained_payload(value)['unique_ndarray_bytes']==32
    value.retained_local_schur_by_class={'a':np.zeros((2,2),complex)}
    assert retained_payload(value)['unique_ndarray_bytes']==96


@pytest.mark.parametrize('cap',[1,10**12])
@pytest.mark.parametrize('failure',[None,'symbolic','save','cleanup'])
def test_symbolic_exit_never_admits_numeric_and_preserves_failures(cap,failure):
    events=[]; saved={}
    class Factor:
        preferred_ordering='unchanged'
        def symbolic(self,a):
            events.append('symbolic')
            if failure=='symbolic':raise ValueError('symbolic failure')
        def info(self,indices):return {'infog':{'16':100,'17':100,'20':20}}
        def symbolic_memory_settings(self):return {'modified':False,'icntl':{'14':20}}
        def numeric(self,*args):pytest.fail('numeric is forbidden')
        def solve(self,*args):pytest.fail('solve is forbidden')
        def destroy(self):
            events.append('destroy')
            if failure=='cleanup':raise ValueError('cleanup failure')
    def save(name,record):
        events.append(name);saved[name]=copy.deepcopy(record)
        if failure=='save' and name=='symbolic_raw':raise OSError('save failure')
    matrix=SimpleNamespace(getComm=lambda:SimpleNamespace(getSize=lambda:1),
                           getSize=lambda:(51272,51272),getInfo=lambda:{})
    request=SimpleNamespace(A=matrix,n_fe=51192,n_aux=80,static_condensed_system=system())
    observer=CondensedSymbolicPreflight(sample=lambda:dict(rss_bytes=100,launch_cap_bytes=cap),
        save=save,marker=lambda *args:None,identity={'fixture':True},factor_factory=lambda a:Factor())
    with pytest.raises(CondensedPreflightExit) as caught:observer(request)
    record=caught.value.record
    assert events[0]=='assembled_preflight' and events[-1]=='destroy'
    assert record['numeric_called'] is record['solve_called'] is False
    if failure is None:
        assert record['status']=='SYMBOLIC_PREFLIGHT_COMPLETED_NUMERIC_NOT_RUN'
        assert record['forecast']['numeric_authorized_by_forecast'] is False
        assert record['forecast']['strict_total_peak_upper_bound_bytes'] is None
        assert events.index('symbolic_raw')<events.index('symbolic_preflight')
    elif failure=='cleanup':assert record['cleanup_errors']
    else:
        assert caught.value.error is not None
        assert record['primary_error']['message']==failure+' failure'


def test_owner_cleanup_deduplicates_aliases_and_preserves_primary_error():
    primary=ValueError('primary')
    stop=CondensedPreflightExit({'status':'failed'},primary)
    calls=[]
    def destroy():calls.append(1);raise RuntimeError('cleanup')
    obj=SimpleNamespace(destroy=destroy)
    stop.release((obj,obj,None))
    assert len(calls)==1 and stop.error is primary
    assert stop.record['status']=='PREFLIGHT_CLEANUP_FAILED'


def test_real_mumps_analysis_reads_controls_without_numeric():
    from petsc4py import PETSc
    from src.solvers.fullspace_v17_p3_oracle import _MumpsFactor
    matrix=PETSc.Mat().createAIJ((3,3),nnz=3,comm=PETSc.COMM_SELF)
    matrix.setValues(range(3),range(3),np.array([[3,1j,0],[1,4,1],[0,1,3]],complex))
    matrix.assemble();factor=None
    try:
        factor=_MumpsFactor(matrix);factor.symbolic(matrix)
        info=factor.info((22,29));controls=factor.symbolic_memory_settings()
        assert {'16','17','20'}<=info['infog'].keys()
        assert controls['modified'] is False and '14' in controls['icntl']
        assert factor.numeric_calls==factor.solve_calls==0
    finally:
        if factor is not None:factor.destroy()
        matrix.destroy()


def test_reference_input_retains_frozen_physics():
    from src.io import load_and_resolve
    from src.runners.fine_reference_preflight import input_identity
    value=load_and_resolve('input/task39extra/original_13p5nm_p6h10_fine_reference.dat').as_jsonable()
    identity=input_identity(value)
    assert identity['original_physical_sha256']=='9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f'
    assert identity['physical_sha256']!=identity['original_physical_sha256']
    value['incidence']['wavelength_nm']=14
    with pytest.raises(ValueError):input_identity(value)


def test_post_release_resource_failure_replaces_success_and_preserves_exception():
    from src.runners.fine_reference_preflight import record_post_release
    record={'status':'SYMBOLIC_PREFLIGHT_COMPLETED_NUMERIC_NOT_RUN'}
    error=RuntimeError('unreadable process status')
    def sample():raise error
    with pytest.raises(RuntimeError) as caught:record_post_release(record,sample)
    assert caught.value is error
    assert record['status']=='SYMBOLIC_PREFLIGHT_FAILED'
    assert record['primary_error']['message']=='unreadable process status'
